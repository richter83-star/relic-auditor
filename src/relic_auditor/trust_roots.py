"""Public verification keys pinned into production builds.

Only public key material belongs here. Release packaging must fail closed while
either service is unprovisioned; private signing keys remain outside the app.
"""

from __future__ import annotations


PRODUCTION_LICENSE_PUBLIC_KEYS: dict[str, bytes] = {}
PRODUCTION_UPDATE_PUBLIC_KEYS: dict[str, bytes] = {}
