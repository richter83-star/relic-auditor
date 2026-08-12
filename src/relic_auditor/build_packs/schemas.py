from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


BUILD_PACK_SCHEMA = "1.0"
APPROVAL_SCHEMA = "1.0"


class BuildPackError(ValueError):
    pass


class EligibilityError(BuildPackError):
    pass


class ApprovalError(BuildPackError):
    pass


class ExportValidationError(BuildPackError):
    pass


class AssetClassification(str, Enum):
    ELIGIBLE = "eligible"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class PreparedBuildPack:
    pack_id: str
    content_hash: str
    content: Mapping[str, Any]
    source_root: Path | None = None

    def public(self) -> dict[str, Any]:
        return {
            "schema_version": BUILD_PACK_SCHEMA,
            "pack_id": self.pack_id,
            "content_hash": self.content_hash,
            **dict(self.content),
        }


@dataclass(frozen=True)
class ApprovalManifest:
    approval_id: str
    content: Mapping[str, Any]

    def public(self) -> dict[str, Any]:
        return {
            "schema_version": APPROVAL_SCHEMA,
            "approval_id": self.approval_id,
            **dict(self.content),
        }


@dataclass(frozen=True)
class ExportResult:
    directory: Path
    pack_id: str
    files: tuple[Path, ...]
    checksum: str
