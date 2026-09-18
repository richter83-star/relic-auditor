"""Offline owner-license issuer. Run on the owner's workstation, never in the app.

Requires an existing Ed25519 private key held outside the repository. This tool
does not create or upload keys and refuses an issuer not pinned in this build.
"""
from __future__ import annotations

import argparse
import base64
import os
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from relic_auditor.build_packs.canonical import canonical_bytes
from relic_auditor.licensing import LicenseClaims, LicenseToken, verify_license_token
from relic_auditor.product_discovery.entitlements import ProductTier
from relic_auditor.trust_roots import OWNER_LICENSE_PUBLIC_KEYS


def issue(private_key: Path, device_id: str, subject: str, days: int, output: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    if private_key.resolve().is_relative_to(repo) or output.resolve().is_relative_to(repo):
        raise ValueError("issuer keys and issued licenses must stay outside the repository")
    if not re.fullmatch(r"device_[0-9a-f]{32}", device_id):
        raise ValueError("copy the exact installation ID from Relic")
    if not 1 <= days <= 90:
        raise ValueError("owner test licenses must expire within 1 to 90 days")
    private = serialization.load_pem_private_key(private_key.read_bytes(), password=None)
    if not isinstance(private, Ed25519PrivateKey):
        raise ValueError("the owner issuer must be an Ed25519 private key")
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key_id = next((key for key, value in OWNER_LICENSE_PUBLIC_KEYS.items() if value == public), None)
    if key_id is None:
        raise ValueError("the supplied issuer is not trusted by this Relic build")
    now = datetime.now(UTC)
    end = (now + timedelta(days=days)).isoformat()
    claims = LicenseClaims(
        license_id=f"owner_test_{uuid.uuid4().hex}", subject=subject,
        tier=ProductTier.PREMIUM, device_id=device_id, issued_at=now.isoformat(),
        expires_at=end, offline_until=end,
    )
    unsigned = LicenseToken(key_id, claims, "pending")
    signature = base64.urlsafe_b64encode(private.sign(unsigned.signed_payload())).decode().rstrip("=")
    token = LicenseToken(key_id, claims, signature)
    verify_license_token(token, public_keys=OWNER_LICENSE_PUBLIC_KEYS, device_id=device_id, now=now)
    output.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as handle:
        handle.write(canonical_bytes(token.public()) + b"\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        issue(args.private_key, args.device_id, args.subject, args.days, args.output)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(f"Premium owner license written to {args.output}")


if __name__ == "__main__":
    main()
