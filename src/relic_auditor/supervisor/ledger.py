from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from ..build_packs.canonical import canonical_bytes
from .schemas import SupervisorError


GENESIS_HASH = "0" * 64


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class AppendOnlyLedger:
    """JSONL audit ledger with an independently verifiable SHA-256 hash chain."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        result: list[dict[str, Any]] = []
        for number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SupervisorError(f"ledger line {number} is invalid JSON") from exc
            if not isinstance(value, dict):
                raise SupervisorError(f"ledger line {number} is not an object")
            result.append(value)
        return result

    def verify(self) -> dict[str, Any]:
        previous = GENESIS_HASH
        entries = self.entries()
        for expected_sequence, entry in enumerate(entries, 1):
            if entry.get("sequence") != expected_sequence:
                raise SupervisorError("ledger sequence is invalid")
            if entry.get("previous_hash") != previous:
                raise SupervisorError("ledger hash chain is invalid")
            content = {key: value for key, value in entry.items() if key != "entry_hash"}
            calculated = hashlib.sha256(canonical_bytes(content)).hexdigest()
            if entry.get("entry_hash") != calculated:
                raise SupervisorError("ledger entry hash is invalid")
            previous = calculated
        return {"valid": True, "entries": len(entries), "head": previous}

    def append(self, event: str, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if not event or len(event) > 120:
            raise SupervisorError("ledger event name is invalid")
        status = self.verify()
        entry = {
            "sequence": int(status["entries"]) + 1,
            "timestamp": _timestamp(),
            "event": event,
            "details": dict(details or {}),
            "previous_hash": status["head"],
        }
        entry["entry_hash"] = hashlib.sha256(canonical_bytes(entry)).hexdigest()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        descriptor = os.open(self.path, flags, 0o600)
        try:
            with os.fdopen(descriptor, "ab", closefd=False) as stream:
                stream.write(canonical_bytes(entry))
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(descriptor)
        return entry
