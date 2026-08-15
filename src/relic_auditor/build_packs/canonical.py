from __future__ import annotations

import hashlib
import json
import os
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def stable_id(prefix: str, value: Any, length: int = 24) -> str:
    return f"{prefix}_{digest(value)[:length]}"


def normalized_relative_path(path: str) -> str:
    raw = unicodedata.normalize("NFC", path.replace("\\", "/"))
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or not raw or "\x00" in raw:
        raise ValueError("path must be a non-empty relative path")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("path traversal is not allowed")
    if ":" in raw:
        raise ValueError("alternate data streams and drive-qualified paths are blocked")
    return candidate.as_posix()


def collision_key(path: str) -> str:
    return unicodedata.normalize("NFC", path).casefold()


def source_root_path_fingerprint(path: Path) -> str:
    """One-way path identity used to keep later workspaces out of the source."""

    normalized = os.path.normcase(str(path.expanduser().resolve()))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
