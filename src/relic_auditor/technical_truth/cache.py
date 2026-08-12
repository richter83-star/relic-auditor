from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


CACHE_SCHEMA = "1.0"


class ParseCache:
    def __init__(self, path: str | None):
        self.path = Path(path).resolve() if path else None
        self.entries: dict[str, Any] = {}
        self.hits = 0
        self.misses = 0
        if self.path and self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if data.get("schema_version") == CACHE_SCHEMA:
                    self.entries = data.get("entries", {})
            except (OSError, json.JSONDecodeError):
                self.entries = {}

    @staticmethod
    def key(path: str, digest: str, family_id: str, adapter_version: str) -> str:
        return hashlib.sha256(f"{path}\x1f{digest}\x1f{family_id}\x1f{adapter_version}".encode()).hexdigest()

    def get(self, key: str):
        if key in self.entries:
            self.hits += 1
            return self.entries[key]
        self.misses += 1
        return None

    def put(self, key: str, value: Any):
        self.entries[key] = value

    def save(self):
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        document = {"schema_version": CACHE_SCHEMA, "entries": dict(sorted(self.entries.items()))}
        temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.path)
