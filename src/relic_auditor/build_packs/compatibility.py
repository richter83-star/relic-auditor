from __future__ import annotations

import json
from pathlib import Path

from .canonical import digest
from .schemas import ExportValidationError, PreparedBuildPack


def load_prepared_pack(path: Path) -> PreparedBuildPack:
    data = json.loads(path.read_text(encoding="utf-8"))
    content = {
        key: value
        for key, value in data.items()
        if key not in {"schema_version", "pack_id", "content_hash"}
    }
    content_hash = digest(content)
    if (
        data.get("content_hash") != content_hash
        or data.get("pack_id") != f"bp_{content_hash[:24]}"
    ):
        raise ExportValidationError("prepared Build Pack failed canonical verification")
    return PreparedBuildPack(str(data["pack_id"]), content_hash, content, None)
