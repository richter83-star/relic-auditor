from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ScanLimits:
    max_file_bytes: int = 10 * 1024 * 1024
    max_sample_bytes: int = 32 * 1024
    max_zip_members: int = 20_000
    max_zip_uncompressed_bytes: int = 2 * 1024 * 1024 * 1024
    max_zip_ratio: int = 250


@dataclass
class FileRecord:
    path: str
    size: int
    extension: str
    source: str = "filesystem"
    archive_path: str | None = None
    sha256: str | None = None
    text: str | None = None
    role: str | None = None
    ignored_reason: str | None = None
    warnings: list[str] = field(default_factory=list)

    def public(self, include_text: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_text:
            data.pop("text", None)
        data["warnings"] = sorted(data["warnings"])
        return data


@dataclass
class ProjectRecord:
    root: str
    kinds: list[str]
    signals: list[str]
    manifests: list[str]
    source_files: int
    test_files: int
    documentation_files: int
    appraisal_category: str = ""
    appraisal_score: int = 0
    appraisal_reasons: list[str] = field(default_factory=list)


@dataclass
class Candidate:
    path: str
    reason: str
    confidence: str
    kind: str
    project_root: str | None = None


@dataclass
class AuditResult:
    target: Path
    files: list[FileRecord]
    projects: list[ProjectRecord]
    archives: list[dict[str, Any]]
    ignored: list[dict[str, Any]]
    warnings: list[str]
    samples: list[dict[str, Any]]
    extract_candidates: list[Candidate]
    archive_candidates: list[Candidate]
    delete_candidates: list[Candidate]
    pivot_suggestions: list[dict[str, Any]]
    duplicate_groups: list[dict[str, Any]]
