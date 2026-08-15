from __future__ import annotations

import base64
import io
import json
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from relic_auditor.licensing import (
    LICENSE_ISSUER,
    LICENSE_SCHEMA,
    LICENSE_SERVICE,
    LicenseActivationError,
    LicenseToken,
    LicenseVerificationError,
    activate_license,
    load_cached_entitlement,
    refresh_license,
    verify_license_token,
)
from relic_auditor.product_discovery.entitlements import ProductTier
from relic_auditor.product_discovery.entitlements import entitlement_for_testing
from relic_auditor.dashboard.core import DashboardOptions, run_dashboard_audit


DEVICE = "device_" + "a" * 32


class MemoryStore:
    def __init__(self) -> None:
        self.value = None

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def delete(self):
        self.value = None


class FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes, *, url: str = "https://licensing.dracanus.ai/response") -> None:
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}
        self._url = url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


@pytest.fixture()
def signing():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private, {"test-key": public}


def _token(private, *, now=None, device=DEVICE, tier="premium", offline_hours=24, expires_days=30):
    current = now or datetime(2026, 8, 15, 12, tzinfo=UTC)
    unsigned = {
        "schema_version": LICENSE_SCHEMA,
        "key_id": "test-key",
        "claims": {
            "license_id": "lic_test_000001",
            "subject": "customer-123",
            "tier": tier,
            "device_id": device,
            "issued_at": current.isoformat().replace("+00:00", "Z"),
            "expires_at": (current + timedelta(days=expires_days)).isoformat().replace("+00:00", "Z"),
            "offline_until": (current + timedelta(hours=offline_hours)).isoformat().replace("+00:00", "Z"),
            "issuer": LICENSE_ISSUER,
            "service": LICENSE_SERVICE,
        },
    }
    parsed = LicenseToken.parse({**unsigned, "signature": "pending"})
    signature = private.sign(parsed.signed_payload())
    return {
        **unsigned,
        "signature": base64.urlsafe_b64encode(signature).decode().rstrip("="),
    }


def test_valid_signed_premium_entitlement(signing) -> None:
    private, keys = signing
    now = datetime(2026, 8, 15, 12, tzinfo=UTC)
    result = verify_license_token(
        _token(private, now=now), public_keys=keys, device_id=DEVICE, now=now
    )
    assert result.tier == ProductTier.PREMIUM
    assert result.source == "verified-signed-license"
    assert result.license_id == "lic_test_000001"


def test_tampered_tier_cannot_promote_entitlement(signing) -> None:
    private, keys = signing
    token = _token(private, tier="pro")
    token["claims"]["tier"] = "premium"
    with pytest.raises(LicenseVerificationError, match="signature"):
        verify_license_token(token, public_keys=keys, device_id=DEVICE)


def test_token_is_bound_to_installation(signing) -> None:
    private, keys = signing
    with pytest.raises(LicenseVerificationError, match="different installation"):
        verify_license_token(
            _token(private),
            public_keys=keys,
            device_id="device_" + "b" * 32,
            now=datetime(2026, 8, 15, 12, tzinfo=UTC),
        )


def test_offline_window_requires_refresh(signing) -> None:
    private, keys = signing
    issued = datetime(2026, 8, 15, 12, tzinfo=UTC)
    with pytest.raises(LicenseVerificationError, match="online refresh"):
        verify_license_token(
            _token(private, now=issued, offline_hours=1),
            public_keys=keys,
            device_id=DEVICE,
            now=issued + timedelta(hours=2),
        )


def test_expired_subscription_fails_closed(signing) -> None:
    private, keys = signing
    issued = datetime(2026, 8, 15, 12, tzinfo=UTC)
    token = _token(private, now=issued, offline_hours=0, expires_days=0)
    with pytest.raises(LicenseVerificationError, match="expired"):
        verify_license_token(
            token,
            public_keys=keys,
            device_id=DEVICE,
            now=issued + timedelta(seconds=1),
        )


def test_cached_license_loads_and_invalid_cache_falls_back_to_free(signing) -> None:
    private, keys = signing
    issued = datetime(2026, 8, 15, 12, tzinfo=UTC)
    store = MemoryStore()
    store.set(json.dumps(_token(private, now=issued)))
    assert load_cached_entitlement(
        public_keys=keys, store=store, device_id=DEVICE, now=issued
    ).tier == ProductTier.PREMIUM
    store.set("not-json")
    assert load_cached_entitlement(
        public_keys=keys, store=store, device_id=DEVICE, now=issued
    ).tier == ProductTier.FREE


def test_unprovisioned_release_remains_free() -> None:
    assert load_cached_entitlement(public_keys={}, store=MemoryStore(), device_id=DEVICE).tier == ProductTier.FREE


def test_dashboard_bundle_preserves_the_verified_entitlement(tmp_path) -> None:
    target = tmp_path / "estate"
    target.mkdir()
    (target / "app.py").write_text("print('static')\n", encoding="utf-8")
    premium = entitlement_for_testing("premium")
    bundle = run_dashboard_audit(
        target,
        DashboardOptions(technical_truth=False),
        entitlement=premium,
    )
    assert bundle.entitlement is premium


def test_activation_verifies_before_storing(signing) -> None:
    private, keys = signing
    issued = datetime.now(UTC)
    token = _token(private, now=issued)
    body = json.dumps({"token": token}).encode()
    store = MemoryStore()
    observed = {}

    def opener(req, **kwargs):
        observed["body"] = json.loads(req.data.decode())
        observed.update(kwargs)
        return FakeResponse(body)

    result = activate_license(
        "RELIC_LICENSE_12345",
        app_version="0.11.0",
        public_keys=keys,
        store=store,
        device_id=DEVICE,
        opener=opener,
    )
    assert result.tier == ProductTier.PREMIUM
    assert json.loads(store.value)["claims"]["tier"] == "premium"
    assert observed["body"]["license_key"] == "RELIC_LICENSE_12345"
    assert "license_key" not in store.value


def test_activation_rejects_unsigned_response_without_storage(signing) -> None:
    private, keys = signing
    token = _token(private, now=datetime.now(UTC))
    token["signature"] = "invalid"
    store = MemoryStore()
    with pytest.raises(LicenseVerificationError):
        activate_license(
            "RELIC_LICENSE_12345",
            app_version="0.11.0",
            public_keys=keys,
            store=store,
            device_id=DEVICE,
            opener=lambda *_a, **_k: FakeResponse(json.dumps({"token": token}).encode()),
        )
    assert store.value is None


def test_activation_rejects_non_https_redirect(signing) -> None:
    _, keys = signing
    with pytest.raises(LicenseActivationError, match="trusted HTTPS origin"):
        activate_license(
            "RELIC_LICENSE_12345",
            app_version="0.11.0",
            public_keys=keys,
            store=MemoryStore(),
            device_id=DEVICE,
            opener=lambda *_a, **_k: FakeResponse(b"{}", url="http://attacker.test"),
        )


def test_activation_rejects_different_https_origin(signing) -> None:
    _, keys = signing
    with pytest.raises(LicenseActivationError, match="trusted HTTPS origin"):
        activate_license(
            "RELIC_LICENSE_12345",
            app_version="0.11.0",
            public_keys=keys,
            store=MemoryStore(),
            device_id=DEVICE,
            opener=lambda *_a, **_k: FakeResponse(
                b"{}", url="https://attacker.test/redirect"
            ),
        )


def test_token_rejects_unknown_top_level_fields(signing) -> None:
    private, keys = signing
    token = _token(private)
    token["debug"] = True
    with pytest.raises(LicenseVerificationError, match="unknown fields"):
        verify_license_token(
            token,
            public_keys=keys,
            device_id=DEVICE,
            now=datetime(2026, 8, 15, 12, tzinfo=UTC),
        )


def test_activation_rejects_invalid_installation_identifier(signing) -> None:
    _, keys = signing
    with pytest.raises(LicenseActivationError, match="installation identifier"):
        activate_license(
            "RELIC_LICENSE_12345",
            app_version="0.11.0",
            public_keys=keys,
            store=MemoryStore(),
            device_id="not-a-device",
        )


def test_refresh_exchanges_cached_token_and_verifies_before_storage(signing) -> None:
    private, keys = signing
    issued = datetime.now(UTC)
    store = MemoryStore()
    old = _token(private, now=issued, offline_hours=1)
    fresh = _token(private, now=issued, offline_hours=48)
    store.set(json.dumps(old))
    observed = {}

    def opener(req, **kwargs):
        observed["body"] = json.loads(req.data.decode())
        observed.update(kwargs)
        return FakeResponse(json.dumps({"token": fresh}).encode())

    entitlement = refresh_license(
        app_version="0.12.0",
        public_keys=keys,
        store=store,
        device_id=DEVICE,
        opener=opener,
    )
    assert entitlement.tier == ProductTier.PREMIUM
    assert entitlement.valid_until == fresh["claims"]["offline_until"]
    assert observed["body"]["token"] == old
    assert json.loads(store.value) == fresh


def test_refresh_fails_closed_without_cache_or_production_keys(signing) -> None:
    _, keys = signing
    with pytest.raises(LicenseActivationError, match="no cached"):
        refresh_license(
            app_version="0.12.0",
            public_keys=keys,
            store=MemoryStore(),
            device_id=DEVICE,
        )
    with pytest.raises(LicenseActivationError, match="not provisioned"):
        refresh_license(
            app_version="0.12.0",
            public_keys={},
            store=MemoryStore(),
            device_id=DEVICE,
        )
