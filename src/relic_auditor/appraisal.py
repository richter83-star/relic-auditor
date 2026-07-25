from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath

from .models import Candidate, FileRecord, ProjectRecord


def appraise(
    files: list[FileRecord],
    projects: list[ProjectRecord],
    ignored: list[dict[str, str]],
    archives: list[dict[str, object]],
) -> tuple[
    list[ProjectRecord],
    list[Candidate],
    list[Candidate],
    list[Candidate],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    for project in projects:
        score = 20
        reasons: list[str] = []
        if project.source_files >= 5:
            score += 25
            reasons.append("substantive source tree")
        elif project.source_files:
            score += 10
            reasons.append("some source code")
        if project.test_files:
            score += min(20, 5 + project.test_files)
            reasons.append("tests present")
        if project.documentation_files:
            score += 10
            reasons.append("documentation present")
        if any("Docker" in kind for kind in project.kinds):
            score += 8
            reasons.append("deployment/container signal")
        if {"Next.js", "FastAPI"}.intersection(project.kinds):
            score += 7
            reasons.append("application framework detected")
        project.appraisal_score = min(score, 100)
        if score >= 75:
            project.appraisal_category = "Crown jewel"
        elif score >= 55:
            project.appraisal_category = "Valuable system"
        elif score >= 35:
            project.appraisal_category = "Salvageable build"
        else:
            project.appraisal_category = "Fragment / needs context"
        project.appraisal_reasons = reasons or ["manifest evidence only"]

    duplicate_groups = _duplicates(files)
    extract_candidates = _extract_candidates(files, projects)
    archive_candidates = _archive_candidates(projects, archives)
    delete_candidates = _delete_candidates(ignored, duplicate_groups)
    pivots = _pivot_suggestions(files, projects)
    return (
        projects,
        extract_candidates,
        archive_candidates,
        delete_candidates,
        pivots,
        duplicate_groups,
    )


def _duplicates(files: list[FileRecord]) -> list[dict[str, object]]:
    grouped: dict[str, list[FileRecord]] = defaultdict(list)
    for record in files:
        if record.sha256 and record.size > 0:
            grouped[record.sha256].append(record)
    groups = []
    for digest, records in sorted(grouped.items()):
        if len(records) < 2:
            continue
        paths = sorted(record.path for record in records)
        groups.append(
            {
                "sha256": digest,
                "size_each": records[0].size,
                "copies": len(records),
                "reclaimable_bytes_if_one_kept": records[0].size * (len(records) - 1),
                "paths": paths,
            }
        )
    return groups


def _extract_candidates(files: list[FileRecord], projects: list[ProjectRecord]) -> list[Candidate]:
    candidates: list[Candidate] = []
    project_roots = [project.root for project in projects]
    for record in files:
        if record.source != "filesystem":
            continue
        parts = {part.lower() for part in PurePosixPath(record.path).parts}
        if record.role not in {"API/routing", "data model", "UI/component"}:
            continue
        if record.size == 0 or record.extension not in {
            ".py",
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
        }:
            continue
        root = _nearest_root(record.path, project_roots)
        if {"components", "packages", "lib", "shared", "core"} & parts:
            candidates.append(
                Candidate(
                    path=record.path,
                    reason=f"Reusable {record.role} in a shared/component-oriented location",
                    confidence="medium",
                    kind="extract",
                    project_root=root,
                )
            )
    return sorted(candidates, key=lambda candidate: candidate.path)[:250]


def _archive_candidates(
    projects: list[ProjectRecord], archives: list[dict[str, object]]
) -> list[Candidate]:
    candidates = [
        Candidate(
            path=project.root,
            reason="Low-evidence project fragment; preserve for context instead of active development",
            confidence="medium",
            kind="archive",
            project_root=project.root,
        )
        for project in projects
        if project.appraisal_score < 35
    ]
    for archive in archives:
        if archive["status"] in {"invalid", "rejected"}:
            candidates.append(
                Candidate(
                    path=str(archive["path"]),
                    reason=f"Archive could not be safely inspected ({archive['status']}); quarantine for review",
                    confidence="high",
                    kind="archive",
                )
            )
    return sorted(candidates, key=lambda candidate: candidate.path)


def _delete_candidates(
    ignored: list[dict[str, str]], duplicate_groups: list[dict[str, object]]
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for item in ignored:
        if item["reason"] in {
            "known junk file",
            "generated, dependency, cache, or VCS directory",
        }:
            candidates.append(
                Candidate(
                    path=item["path"],
                    reason=item["reason"],
                    confidence="high" if item["reason"] == "known junk file" else "medium",
                    kind="delete-review",
                )
            )
    for group in duplicate_groups:
        for path in group["paths"][1:]:  # type: ignore[index]
            candidates.append(
                Candidate(
                    path=str(path),
                    reason=f"Byte-identical duplicate; verify preferred copy before deleting ({group['sha256'][:12]})",
                    confidence="high",
                    kind="delete-review",
                )
            )
    return sorted(candidates, key=lambda candidate: candidate.path)


def _pivot_suggestions(
    files: list[FileRecord], projects: list[ProjectRecord]
) -> list[dict[str, object]]:
    kinds = {kind for project in projects for kind in project.kinds}
    roles = {record.role for record in files}
    suggestions: list[dict[str, object]] = []
    if "Next.js" in kinds and "FastAPI" in kinds:
        suggestions.append(
            {
                "title": "Consolidate into a full-stack product shell",
                "evidence": ["Next.js frontend detected", "FastAPI backend detected"],
                "idea": "Preserve the strongest UI and API contracts as one focused application.",
                "confidence": "high",
            }
        )
    if len(projects) >= 3:
        suggestions.append(
            {
                "title": "Create a reusable internal platform layer",
                "evidence": [f"{len(projects)} project roots detected"],
                "idea": "Extract repeated authentication, data, UI, and deployment patterns before maintaining separate forks.",
                "confidence": "medium",
            }
        )
    if {"API/routing", "data model"}.issubset(roles) and "UI/component" not in roles:
        suggestions.append(
            {
                "title": "Reframe backend assets as an API product",
                "evidence": ["API routes and data models detected", "No strong UI component signal"],
                "idea": "Package the working backend capability behind a documented API instead of rebuilding a full interface.",
                "confidence": "medium",
            }
        )
    if "UI/component" in roles and "API/routing" not in roles:
        suggestions.append(
            {
                "title": "Extract a design system or interactive prototype",
                "evidence": ["UI components detected", "No strong API routing signal"],
                "idea": "Treat the interface work as a reusable component kit or validated product concept.",
                "confidence": "medium",
            }
        )
    if not suggestions:
        suggestions.append(
            {
                "title": "Preserve and cluster before choosing a pivot",
                "evidence": ["No deterministic cross-project pattern crossed the suggestion threshold"],
                "idea": "Use appraisal categories and duplicate groups to form coherent project clusters; reserve semantic pivoting for the later reasoning hook.",
                "confidence": "low",
            }
        )
    return suggestions


def _nearest_root(path: str, roots: list[str]) -> str | None:
    matches = [root for root in roots if root == "." or path.startswith(f"{root}/")]
    return max(matches, key=len, default=None)
