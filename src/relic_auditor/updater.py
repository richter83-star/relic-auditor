"""Fail-closed application updates for installed Relic Auditor builds.

This module is deliberately separate from the scanner.  It never receives a
scan target and cannot execute anything found in one.  Its only executable
input is a Windows installer that matches a first-party HTTPS manifest, its
declared SHA-256 digest, and the pinned Dracanus AI Authenticode publisher.
"""

from __future__ import annotations

import hashlib
import base64
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import total_ordering
from pathlib import Path
from typing import Any, BinaryIO, Callable, Mapping
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .build_packs.canonical import canonical_bytes
from .trust_roots import PRODUCTION_UPDATE_PUBLIC_KEYS


MANIFEST_SCHEMA_VERSION = 2
LEGACY_MANIFEST_SCHEMA_VERSION = 1
DEFAULT_UPDATE_CHANNEL = "stable"
DEFAULT_UPDATE_MANIFEST_URL = (
    "https://relic-auditor.briandrichter.chatgpt.site/downloads/stable.json"
)
TRUSTED_AUTHENTICODE_PUBLISHER = "Dracanus AI"
MAX_MANIFEST_BYTES = 128 * 1024
MAX_INSTALLER_BYTES = 750 * 1024 * 1024
AUTO_CHECK_INTERVAL = timedelta(hours=24)
FAILED_CHECK_RETRY_INTERVAL = timedelta(hours=6)

_VERSION_RE = re.compile(
    r"^v?(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?$"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RELIC_INSTALLER_RE = re.compile(
    r"^Relic-Auditor-Setup-\d+\.\d+\.\d+"
    r"(?:-[0-9A-Za-z.-]+)?-x64\.exe(?:\.part)?$",
    re.IGNORECASE,
)


class UpdateError(RuntimeError):
    """Base class for updater failures safe to display to the user."""


class UpdateManifestError(UpdateError):
    """The update manifest is missing, malformed, or unsafe."""


class UpdateDownloadError(UpdateError):
    """The installer download did not match its manifest."""


class UpdateVerificationError(UpdateError):
    """The downloaded installer did not pass publisher verification."""


@total_ordering
@dataclass(frozen=True)
class ReleaseVersion:
    """A small SemVer-compatible release version used without dependencies."""

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()

    @classmethod
    def parse(cls, value: str) -> "ReleaseVersion":
        match = _VERSION_RE.fullmatch(str(value).strip())
        if match is None:
            raise UpdateManifestError(f"Invalid release version: {value!r}")
        prerelease = tuple((match.group("prerelease") or "").split("."))
        if prerelease == ("",):
            prerelease = ()
        return cls(
            int(match.group("major")),
            int(match.group("minor")),
            int(match.group("patch")),
            prerelease,
        )

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{'.'.join(self.prerelease)}" if self.prerelease else base

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, ReleaseVersion):
            return NotImplemented
        left = (self.major, self.minor, self.patch)
        right = (other.major, other.minor, other.patch)
        if left != right:
            return left < right
        if not self.prerelease:
            return False if not other.prerelease else False
        if not other.prerelease:
            return True
        for left_token, right_token in zip(self.prerelease, other.prerelease):
            if left_token == right_token:
                continue
            left_number = left_token.isdigit()
            right_number = right_token.isdigit()
            if left_number and right_number:
                return int(left_token) < int(right_token)
            if left_number != right_number:
                return left_number
            return left_token < right_token
        return len(self.prerelease) < len(other.prerelease)


@dataclass(frozen=True)
class InstallerAsset:
    filename: str
    url: str
    sha256: str
    size: int


@dataclass(frozen=True)
class UpdateManifest:
    schema_version: int
    channel: str
    version: ReleaseVersion
    published_at: datetime
    release_notes: tuple[str, ...]
    release_notes_url: str | None
    installer: InstallerAsset
    key_id: str | None = None
    signature: str | None = None
    signature_verified: bool = False

    def is_newer_than(self, current_version: str | ReleaseVersion) -> bool:
        current = (
            current_version
            if isinstance(current_version, ReleaseVersion)
            else ReleaseVersion.parse(current_version)
        )
        return self.version > current


@dataclass(frozen=True)
class AuthenticodeResult:
    status: str
    subject: str
    trusted: bool


@dataclass(frozen=True)
class PreparedUpdate:
    manifest: UpdateManifest
    installer_path: Path
    authenticode: AuthenticodeResult


@dataclass(frozen=True)
class UpdateCheckState:
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None


def _require_https(value: object, field: str) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise UpdateManifestError(f"{field} must be an absolute HTTPS URL")
    if parsed.username or parsed.password:
        raise UpdateManifestError(f"{field} must not contain credentials")
    return url


def _published_at(value: object) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UpdateManifestError("published_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise UpdateManifestError("published_at must include a timezone")
    return parsed.astimezone(UTC)


def _signature_bytes(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (TypeError, ValueError) as exc:
        raise UpdateManifestError("Update manifest signature encoding is invalid") from exc


def _verify_manifest_signature(
    decoded: dict[str, Any], public_keys: Mapping[str, bytes]
) -> tuple[str, str]:
    if int(decoded.get("schema_version", 0)) != MANIFEST_SCHEMA_VERSION:
        raise UpdateManifestError("Unsigned legacy update manifests are not trusted")
    key_id = str(decoded.get("key_id") or "").strip()
    signature = str(decoded.get("signature") or "").strip()
    if not key_id or len(key_id) > 100 or not signature:
        raise UpdateManifestError("Update manifest signature metadata is missing")
    key = public_keys.get(key_id)
    if key is None:
        raise UpdateManifestError("Update manifest signing key is not trusted")
    signed = dict(decoded)
    signed.pop("signature", None)
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(
            _signature_bytes(signature), canonical_bytes(signed)
        )
    except (ValueError, InvalidSignature) as exc:
        raise UpdateManifestError("Update manifest signature is invalid") from exc
    return key_id, signature


def parse_update_manifest(
    payload: bytes | str | dict[str, Any],
    *,
    public_keys: Mapping[str, bytes] | None = None,
    require_signature: bool = False,
) -> UpdateManifest:
    """Parse and strictly validate a stable-channel update manifest."""

    if isinstance(payload, (bytes, str)):
        try:
            decoded = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UpdateManifestError("Update manifest is not valid UTF-8 JSON") from exc
    else:
        decoded = payload
    if not isinstance(decoded, dict):
        raise UpdateManifestError("Update manifest must be a JSON object")

    try:
        schema_version = int(decoded.get("schema_version"))
    except (TypeError, ValueError) as exc:
        raise UpdateManifestError("Unsupported update manifest schema") from exc
    if schema_version not in {LEGACY_MANIFEST_SCHEMA_VERSION, MANIFEST_SCHEMA_VERSION}:
        raise UpdateManifestError("Unsupported update manifest schema")
    signature_verified = False
    key_id: str | None = None
    signature: str | None = None
    if schema_version == MANIFEST_SCHEMA_VERSION:
        required = {
            "schema_version",
            "key_id",
            "channel",
            "version",
            "published_at",
            "release_notes",
            "installer",
            "signature",
        }
        allowed = required | {"release_notes_url"}
        if not required <= set(decoded) or not set(decoded) <= allowed:
            raise UpdateManifestError(
                "Signed update manifest contains missing or unknown fields"
            )
        key_id = str(decoded.get("key_id") or "").strip() or None
        signature = str(decoded.get("signature") or "").strip() or None
    if require_signature:
        if not public_keys:
            raise UpdateManifestError("Signed update verification is not provisioned in this build")
        key_id, signature = _verify_manifest_signature(decoded, public_keys)
        signature_verified = True

    channel = str(decoded.get("channel") or "").strip().lower()
    if channel != DEFAULT_UPDATE_CHANNEL:
        raise UpdateManifestError("Only the stable update channel is supported")

    version = ReleaseVersion.parse(str(decoded.get("version") or ""))
    published_at = _published_at(decoded.get("published_at"))

    notes_value = decoded.get("release_notes", [])
    if not isinstance(notes_value, list) or len(notes_value) > 20:
        raise UpdateManifestError("release_notes must be a list of at most 20 items")
    notes: list[str] = []
    for item in notes_value:
        note = str(item).strip()
        if not note or len(note) > 500:
            raise UpdateManifestError("Each release note must contain 1-500 characters")
        notes.append(note)

    notes_url_value = decoded.get("release_notes_url")
    notes_url = (
        _require_https(notes_url_value, "release_notes_url")
        if notes_url_value
        else None
    )

    installer_value = decoded.get("installer")
    if not isinstance(installer_value, dict):
        raise UpdateManifestError("installer must be a JSON object")
    if schema_version == MANIFEST_SCHEMA_VERSION and set(installer_value) != {
        "filename",
        "url",
        "sha256",
        "size",
    }:
        raise UpdateManifestError("Signed installer contains missing or unknown fields")
    filename = str(installer_value.get("filename") or "").strip()
    if (
        not filename
        or Path(filename).name != filename
        or not filename.lower().endswith(".exe")
        or len(filename) > 180
    ):
        raise UpdateManifestError("installer.filename must be a safe .exe filename")
    installer_url = _require_https(installer_value.get("url"), "installer.url")
    sha256 = str(installer_value.get("sha256") or "").strip().lower()
    if _SHA256_RE.fullmatch(sha256) is None:
        raise UpdateManifestError("installer.sha256 must be a lowercase SHA-256 digest")
    try:
        size = int(installer_value.get("size"))
    except (TypeError, ValueError) as exc:
        raise UpdateManifestError("installer.size must be an integer") from exc
    if size <= 0 or size > MAX_INSTALLER_BYTES:
        raise UpdateManifestError("installer.size is outside the allowed range")

    return UpdateManifest(
        schema_version=schema_version,
        channel=channel,
        version=version,
        published_at=published_at,
        release_notes=tuple(notes),
        release_notes_url=notes_url,
        installer=InstallerAsset(filename, installer_url, sha256, size),
        key_id=key_id,
        signature=signature,
        signature_verified=signature_verified,
    )


def fetch_update_manifest(
    url: str = DEFAULT_UPDATE_MANIFEST_URL,
    *,
    timeout: float = 8.0,
    opener: Callable[..., Any] = urlopen,
    public_keys: Mapping[str, bytes] = PRODUCTION_UPDATE_PUBLIC_KEYS,
) -> UpdateManifest:
    """Fetch a bounded HTTPS manifest and validate any redirect target."""

    manifest_url = _require_https(url, "manifest URL")
    request = Request(
        manifest_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Relic-Auditor-Updater/1",
            "Cache-Control": "no-cache",
        },
    )
    try:
        with opener(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            if status != 200:
                raise UpdateManifestError(f"Update service returned HTTP {status}")
            final_url = getattr(response, "geturl", lambda: manifest_url)()
            _require_https(final_url, "manifest redirect")
            length = response.headers.get("Content-Length") if response.headers else None
            if length and int(length) > MAX_MANIFEST_BYTES:
                raise UpdateManifestError("Update manifest is too large")
            data = response.read(MAX_MANIFEST_BYTES + 1)
    except UpdateError:
        raise
    except (OSError, TimeoutError, ValueError) as exc:
        raise UpdateManifestError(f"Could not reach the update service: {exc}") from exc
    if len(data) > MAX_MANIFEST_BYTES:
        raise UpdateManifestError("Update manifest is too large")
    return parse_update_manifest(
        data,
        public_keys=public_keys,
        require_signature=True,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def default_update_directory() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "Relic Auditor" / "Updates"
    return Path.home() / ".local" / "share" / "Relic Auditor" / "Updates"


def default_update_state_path() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "Relic Auditor" / "update-state.json"
    return Path.home() / ".config" / "Relic Auditor" / "update-state.json"


def _response_read(response: BinaryIO, size: int) -> bytes:
    return response.read(size)


def _remove_superseded_installers(destination: Path, keep_filename: str) -> None:
    """Keep only the current Relic installer candidate in the private cache."""

    keep = {keep_filename.casefold(), f"{keep_filename}.part".casefold()}
    for candidate in destination.iterdir():
        if (
            candidate.is_file()
            and candidate.name.casefold() not in keep
            and _RELIC_INSTALLER_RE.fullmatch(candidate.name)
        ):
            candidate.unlink(missing_ok=True)


def download_installer(
    manifest: UpdateManifest,
    destination: Path | None = None,
    *,
    timeout: float = 30.0,
    opener: Callable[..., Any] = urlopen,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Download the declared installer atomically and verify size and SHA-256."""

    asset = manifest.installer
    destination = (destination or default_update_directory()).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    final_path = destination / asset.filename
    partial_path = destination / f"{asset.filename}.part"
    _remove_superseded_installers(destination, asset.filename)

    if final_path.is_file():
        if final_path.stat().st_size == asset.size and sha256_file(final_path) == asset.sha256:
            if progress:
                progress(asset.size, asset.size)
            return final_path
        final_path.unlink()

    request = Request(
        asset.url,
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": "Relic-Auditor-Updater/1",
            "Cache-Control": "no-cache",
        },
    )
    digest = hashlib.sha256()
    written = 0
    try:
        with opener(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            if status != 200:
                raise UpdateDownloadError(f"Installer service returned HTTP {status}")
            final_url = getattr(response, "geturl", lambda: asset.url)()
            _require_https(final_url, "installer redirect")
            length = response.headers.get("Content-Length") if response.headers else None
            if length and int(length) != asset.size:
                raise UpdateDownloadError("Installer size does not match the manifest")
            with partial_path.open("wb") as output:
                while True:
                    block = _response_read(response, 1024 * 1024)
                    if not block:
                        break
                    written += len(block)
                    if written > asset.size or written > MAX_INSTALLER_BYTES:
                        raise UpdateDownloadError("Installer exceeded its declared size")
                    output.write(block)
                    digest.update(block)
                    if progress:
                        progress(written, asset.size)
                output.flush()
                os.fsync(output.fileno())
        if written != asset.size:
            raise UpdateDownloadError("Installer size does not match the manifest")
        if digest.hexdigest() != asset.sha256:
            raise UpdateDownloadError("Installer SHA-256 verification failed")
        os.replace(partial_path, final_path)
        return final_path
    except UpdateError:
        partial_path.unlink(missing_ok=True)
        raise
    except (OSError, TimeoutError, ValueError) as exc:
        partial_path.unlink(missing_ok=True)
        raise UpdateDownloadError(f"Could not download the installer: {exc}") from exc


def verify_authenticode(
    installer_path: Path,
    *,
    runner: Callable[..., Any] = subprocess.run,
    platform: str | None = None,
) -> AuthenticodeResult:
    """Verify the installer with Windows and pin the expected publisher."""

    platform = platform or sys.platform
    if platform != "win32":
        raise UpdateVerificationError("Installer verification requires Windows")
    path = installer_path.expanduser().resolve(strict=True)
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    powershell = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not powershell.is_file():
        raise UpdateVerificationError("Windows signature verification is unavailable")
    script = (
        "$ErrorActionPreference='Stop';"
        "$s=Get-AuthenticodeSignature -LiteralPath $env:RELIC_UPDATE_INSTALLER_PATH;"
        "$publisher=if($s.SignerCertificate){"
        "$s.SignerCertificate.GetNameInfo("
        "[System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName,"
        "$false)}else{''};"
        "[pscustomobject]@{status=[string]$s.Status;subject=[string]$publisher}"
        "|ConvertTo-Json -Compress"
    )
    environment = os.environ.copy()
    environment["RELIC_UPDATE_INSTALLER_PATH"] = str(path)
    try:
        completed = runner(
            [
                str(powershell),
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=30.0,
            check=False,
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateVerificationError(f"Windows signature verification failed: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown error").strip()
        raise UpdateVerificationError(f"Windows signature verification failed: {detail}")
    try:
        payload = json.loads(completed.stdout)
        status = str(payload.get("status") or "Unknown")
        subject = str(payload.get("subject") or "")
    except (AttributeError, json.JSONDecodeError) as exc:
        raise UpdateVerificationError("Windows returned an invalid signature result") from exc
    trusted = (
        status.casefold() == "valid"
        and subject.strip().casefold() == TRUSTED_AUTHENTICODE_PUBLISHER.casefold()
    )
    return AuthenticodeResult(status=status, subject=subject, trusted=trusted)


def prepare_update(
    manifest: UpdateManifest,
    destination: Path | None = None,
    *,
    opener: Callable[..., Any] = urlopen,
    progress: Callable[[int, int], None] | None = None,
    signature_verifier: Callable[[Path], AuthenticodeResult] = verify_authenticode,
) -> PreparedUpdate:
    """Download, hash, and publisher-verify an installer before it is runnable."""

    path = download_installer(
        manifest,
        destination,
        opener=opener,
        progress=progress,
    )
    signature = signature_verifier(path)
    if not signature.trusted:
        path.unlink(missing_ok=True)
        raise UpdateVerificationError(
            "The installer is not signed by the trusted Dracanus AI publisher "
            f"(Windows status: {signature.status})."
        )
    return PreparedUpdate(manifest, path, signature)


def launch_prepared_update(
    prepared: PreparedUpdate,
    *,
    launcher: Callable[..., Any] = subprocess.Popen,
    signature_verifier: Callable[[Path], AuthenticodeResult] = verify_authenticode,
    platform: str | None = None,
) -> None:
    """Re-verify immediately before launching the fixed-argument Inno installer."""

    platform = platform or sys.platform
    if platform != "win32":
        raise UpdateVerificationError("Installing an update requires Windows")
    path = prepared.installer_path.resolve(strict=True)
    asset = prepared.manifest.installer
    if path.stat().st_size != asset.size or sha256_file(path) != asset.sha256:
        raise UpdateVerificationError("Installer changed after verification")
    signature = signature_verifier(path)
    if not signature.trusted:
        raise UpdateVerificationError("Installer publisher changed after verification")
    try:
        launcher(
            [str(path), "/SP-", "/CLOSEAPPLICATIONS", "/NORESTART"],
            shell=False,
            close_fds=True,
        )
    except OSError as exc:
        raise UpdateError(f"Could not start the verified installer: {exc}") from exc


def load_update_check_state(path: Path | None = None) -> UpdateCheckState:
    state_path = path or default_update_state_path()
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return UpdateCheckState()

    def parsed(name: str) -> datetime | None:
        value = payload.get(name)
        if not value:
            return None
        try:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if result.tzinfo is None:
            return None
        return result.astimezone(UTC)

    return UpdateCheckState(parsed("last_attempt_at"), parsed("last_success_at"))


def save_update_check_state(
    *,
    success: bool,
    path: Path | None = None,
    now: datetime | None = None,
) -> None:
    state_path = path or default_update_state_path()
    current = load_update_check_state(state_path)
    timestamp = (now or datetime.now(UTC)).astimezone(UTC)
    payload = {
        "schema_version": 1,
        "last_attempt_at": timestamp.isoformat().replace("+00:00", "Z"),
        "last_success_at": (
            timestamp if success else current.last_success_at
        ).isoformat().replace("+00:00", "Z")
        if (success or current.last_success_at)
        else None,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix(f"{state_path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, state_path)


def should_check_automatically(
    path: Path | None = None,
    *,
    now: datetime | None = None,
) -> bool:
    state = load_update_check_state(path)
    if state.last_attempt_at is None:
        return True
    current = (now or datetime.now(UTC)).astimezone(UTC)
    interval = (
        AUTO_CHECK_INTERVAL
        if state.last_success_at == state.last_attempt_at
        else FAILED_CHECK_RETRY_INTERVAL
    )
    return current - state.last_attempt_at >= interval
