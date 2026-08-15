from __future__ import annotations

import base64
import json
import os
import platform
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib import request
from urllib.parse import urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .build_packs.canonical import canonical_bytes
from .product_discovery.entitlements import (
    Entitlement,
    FREE_ENTITLEMENT,
    ProductTier,
)


LICENSE_SCHEMA = 1
MAX_LICENSE_RESPONSE_BYTES = 128 * 1024
LICENSE_ISSUER = "Dracanus AI"
LICENSE_SERVICE = "Relic Auditor"
DEFAULT_ACTIVATION_URL = "https://licensing.dracanus.ai/v1/relic-auditor/activate"
KEYRING_SERVICE = "Relic Auditor License"
KEYRING_ACCOUNT = "active-entitlement"

# Release builds fail closed until the licensing backend is provisioned and its
# KMS-held signing key's public half is pinned here. Private signing material is
# never generated, stored, or distributed with the desktop application.
PRODUCTION_PUBLIC_KEYS: dict[str, bytes] = {}


class LicenseError(RuntimeError):
    pass


class LicenseStorageError(LicenseError):
    pass


class LicenseVerificationError(LicenseError):
    pass


class LicenseActivationError(LicenseError):
    pass


def _utc(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise LicenseVerificationError("license timestamp is invalid") from exc
    if result.tzinfo is None:
        raise LicenseVerificationError("license timestamp must include a timezone")
    return result.astimezone(UTC)


def _b64decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise LicenseVerificationError("license signature encoding is invalid") from exc


@dataclass(frozen=True)
class LicenseClaims:
    license_id: str
    subject: str
    tier: ProductTier
    device_id: str
    issued_at: str
    expires_at: str
    offline_until: str
    issuer: str = LICENSE_ISSUER
    service: str = LICENSE_SERVICE

    def public(self) -> dict[str, str]:
        return {
            "license_id": self.license_id,
            "subject": self.subject,
            "tier": self.tier.value,
            "device_id": self.device_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "offline_until": self.offline_until,
            "issuer": self.issuer,
            "service": self.service,
        }


@dataclass(frozen=True)
class LicenseToken:
    key_id: str
    claims: LicenseClaims
    signature: str

    def signed_payload(self) -> bytes:
        return canonical_bytes(
            {
                "schema_version": LICENSE_SCHEMA,
                "key_id": self.key_id,
                "claims": self.claims.public(),
            }
        )

    def public(self) -> dict[str, Any]:
        return {
            "schema_version": LICENSE_SCHEMA,
            "key_id": self.key_id,
            "claims": self.claims.public(),
            "signature": self.signature,
        }

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> "LicenseToken":
        if set(value) != {"schema_version", "key_id", "claims", "signature"}:
            raise LicenseVerificationError("license token contains missing or unknown fields")
        if value.get("schema_version") != LICENSE_SCHEMA:
            raise LicenseVerificationError("license schema is unsupported")
        raw = value.get("claims")
        if not isinstance(raw, dict):
            raise LicenseVerificationError("license claims are missing")
        expected = {
            "license_id",
            "subject",
            "tier",
            "device_id",
            "issued_at",
            "expires_at",
            "offline_until",
            "issuer",
            "service",
        }
        if set(raw) != expected:
            raise LicenseVerificationError("license claims contain missing or unknown fields")
        try:
            claims = LicenseClaims(
                license_id=str(raw["license_id"]),
                subject=str(raw["subject"]),
                tier=ProductTier(str(raw["tier"])),
                device_id=str(raw["device_id"]),
                issued_at=str(raw["issued_at"]),
                expires_at=str(raw["expires_at"]),
                offline_until=str(raw["offline_until"]),
                issuer=str(raw["issuer"]),
                service=str(raw["service"]),
            )
        except (KeyError, ValueError) as exc:
            raise LicenseVerificationError("license claims are invalid") from exc
        token = cls(str(value.get("key_id", "")), claims, str(value.get("signature", "")))
        if not token.key_id or len(token.key_id) > 100 or not token.signature:
            raise LicenseVerificationError("license key identifier or signature is invalid")
        return token


def verify_license_token(
    token: LicenseToken | Mapping[str, Any],
    *,
    public_keys: Mapping[str, bytes],
    device_id: str,
    now: datetime | None = None,
) -> Entitlement:
    candidate = token if isinstance(token, LicenseToken) else LicenseToken.parse(token)
    key = public_keys.get(candidate.key_id)
    if key is None:
        raise LicenseVerificationError("license signing key is not trusted")
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(
            _b64decode(candidate.signature), candidate.signed_payload()
        )
    except (ValueError, InvalidSignature) as exc:
        raise LicenseVerificationError("license signature is invalid") from exc
    claims = candidate.claims
    if claims.issuer != LICENSE_ISSUER or claims.service != LICENSE_SERVICE:
        raise LicenseVerificationError("license issuer or service is invalid")
    if not re.fullmatch(r"device_[0-9a-f]{32}", device_id):
        raise LicenseVerificationError("installation identifier is invalid")
    if claims.device_id != device_id:
        raise LicenseVerificationError("license is activated for a different installation")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{6,200}", claims.license_id):
        raise LicenseVerificationError("license identifier is invalid")
    if not claims.subject or len(claims.subject) > 200:
        raise LicenseVerificationError("license subject is invalid")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    issued = _utc(claims.issued_at)
    expires = _utc(claims.expires_at)
    offline = _utc(claims.offline_until)
    if issued > current:
        raise LicenseVerificationError("license is not valid yet")
    if offline > expires:
        raise LicenseVerificationError("license offline window exceeds its subscription term")
    if current > expires:
        raise LicenseVerificationError("license subscription has expired")
    if current > offline:
        raise LicenseVerificationError("license needs an online refresh")
    return Entitlement(
        tier=claims.tier,
        subject=claims.subject,
        source="verified-signed-license",
        license_id=claims.license_id,
        valid_until=claims.offline_until,
    )


class SecretStore(Protocol):
    def get(self) -> str | None: ...
    def set(self, value: str) -> None: ...
    def delete(self) -> None: ...


class KeyringLicenseStore:
    """OS credential-vault storage. No plaintext token fallback is permitted."""

    def get(self) -> str | None:
        try:
            import keyring

            return keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
        except Exception as exc:
            raise LicenseStorageError("the operating-system credential vault is unavailable") from exc

    def set(self, value: str) -> None:
        try:
            import keyring

            keyring.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, value)
        except Exception as exc:
            raise LicenseStorageError("the operating-system credential vault rejected the license") from exc

    def delete(self) -> None:
        try:
            import keyring

            keyring.delete_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
        except keyring.errors.PasswordDeleteError:
            return
        except Exception as exc:
            raise LicenseStorageError("the operating-system credential vault could not remove the license") from exc


def default_license_directory() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "Dracanus AI" / "Relic Auditor" / "License"
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "relic-auditor" / "license"


def installation_id(path: Path | None = None) -> str:
    target = (path or default_license_directory() / "installation-id").expanduser()
    try:
        existing = target.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        existing = ""
    if re.fullmatch(r"device_[0-9a-f]{32}", existing):
        return existing
    target.parent.mkdir(parents=True, exist_ok=True)
    value = f"device_{uuid.uuid4().hex}"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(value + "\n", encoding="ascii")
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, target)
    return value


def activate_license(
    license_key: str,
    *,
    app_version: str,
    public_keys: Mapping[str, bytes] = PRODUCTION_PUBLIC_KEYS,
    store: SecretStore | None = None,
    device_id: str | None = None,
    activation_url: str = DEFAULT_ACTIVATION_URL,
    opener: Callable[..., Any] = request.urlopen,
    timeout_seconds: float = 20.0,
) -> Entitlement:
    cleaned = license_key.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{12,200}", cleaned):
        raise LicenseActivationError("license key format is invalid")
    if not public_keys:
        raise LicenseActivationError("license activation is not provisioned in this build")
    parsed = urlparse(activation_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise LicenseActivationError("license activation URL must be credential-free HTTPS")
    active_device = device_id or installation_id()
    if not re.fullmatch(r"device_[0-9a-f]{32}", active_device):
        raise LicenseActivationError("installation identifier is invalid")
    payload = canonical_bytes(
        {
            "schema_version": LICENSE_SCHEMA,
            "license_key": cleaned,
            "device_id": active_device,
            "app_version": app_version,
            "platform": platform.system().lower(),
        }
    )
    req = request.Request(
        activation_url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with opener(req, timeout=timeout_seconds) as response:
            final = urlparse(response.geturl())
            original_port = parsed.port or 443
            final_port = final.port or 443
            if (
                final.scheme != "https"
                or not final.netloc
                or final.username
                or final.password
                or final.hostname != parsed.hostname
                or final_port != original_port
            ):
                raise LicenseActivationError(
                    "license activation redirected outside the trusted HTTPS origin"
                )
            length = response.headers.get("Content-Length")
            if length:
                try:
                    declared_length = int(length)
                except ValueError as exc:
                    raise LicenseActivationError(
                        "license activation returned an invalid content length"
                    ) from exc
                if declared_length < 0 or declared_length > MAX_LICENSE_RESPONSE_BYTES:
                    raise LicenseActivationError("license activation response is oversized")
            raw = response.read(MAX_LICENSE_RESPONSE_BYTES + 1)
    except LicenseActivationError:
        raise
    except Exception as exc:
        raise LicenseActivationError("license activation service is unavailable") from exc
    if len(raw) > MAX_LICENSE_RESPONSE_BYTES:
        raise LicenseActivationError("license activation response is oversized")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LicenseActivationError("license activation returned invalid data") from exc
    if not isinstance(value, dict) or not isinstance(value.get("token"), dict):
        raise LicenseActivationError("license activation returned no signed entitlement")
    entitlement = verify_license_token(
        value["token"], public_keys=public_keys, device_id=active_device
    )
    (store or KeyringLicenseStore()).set(
        json.dumps(value["token"], separators=(",", ":"), sort_keys=True)
    )
    return entitlement


def load_cached_entitlement(
    *,
    public_keys: Mapping[str, bytes] = PRODUCTION_PUBLIC_KEYS,
    store: SecretStore | None = None,
    device_id: str | None = None,
    now: datetime | None = None,
) -> Entitlement:
    if not public_keys:
        return FREE_ENTITLEMENT
    try:
        encoded = (store or KeyringLicenseStore()).get()
        if not encoded:
            return FREE_ENTITLEMENT
        value = json.loads(encoded)
        if not isinstance(value, dict):
            return FREE_ENTITLEMENT
        return verify_license_token(
            value,
            public_keys=public_keys,
            device_id=device_id or installation_id(),
            now=now,
        )
    except (LicenseError, json.JSONDecodeError, OSError):
        return FREE_ENTITLEMENT


def deactivate_license(*, store: SecretStore | None = None) -> None:
    (store or KeyringLicenseStore()).delete()
