from __future__ import annotations

from pathlib import Path

from .appraisal import appraise
from .detectors import detect_projects
from .models import AuditResult, ScanLimits
from .scanner import EstateScanner


def audit_estate(
    target: Path,
    *,
    limits: ScanLimits | None = None,
    include_hidden: bool = False,
) -> AuditResult:
    active_limits = limits or ScanLimits()
    scanner = EstateScanner(target, active_limits, include_hidden=include_hidden)
    files, archives, ignored, warnings, samples = scanner.scan()
    projects = detect_projects(files)
    (
        projects,
        extract_candidates,
        archive_candidates,
        delete_candidates,
        pivots,
        duplicate_groups,
    ) = appraise(files, projects, ignored, archives)
    return AuditResult(
        target=target.resolve(),
        files=files,
        projects=projects,
        archives=archives,
        ignored=ignored,
        warnings=warnings,
        samples=samples,
        extract_candidates=extract_candidates,
        archive_candidates=archive_candidates,
        delete_candidates=delete_candidates,
        pivot_suggestions=pivots,
        duplicate_groups=duplicate_groups,
    )
