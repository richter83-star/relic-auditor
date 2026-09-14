"""Public verification keys pinned into production builds.

Only public key material belongs here. Release packaging must fail closed while
either service is unprovisioned; private signing keys remain outside the app.
"""

from __future__ import annotations


PRODUCTION_LICENSE_PUBLIC_KEYS: dict[str, bytes] = {}
PRODUCTION_UPDATE_PUBLIC_KEYS: dict[str, bytes] = {}

# Offline owner testing has its own issuer. Only this public verification key
# ships in the app; its private half is held separately by the project owner.
# This does not provision the commercial activation or update services.
OWNER_LICENSE_PUBLIC_KEYS: dict[str, bytes] = {
    "owner-test-2026-09": bytes.fromhex(
        "6bc069ececcc31cc84896dc67ccc283f76b912100bab534890c3c6f23e676e37"
    ),
}
