from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import AuditResult, Candidate


OUTPUT_FILENAMES = {
    "estate": "estate-report.md",
    "architecture": "architecture-map.json",
    "extract": "extract-candidates.json",
    "archive": "archive-candidates.json",
    "delete": "delete-candidates.json",
    "pivots": "pivot-suggestions.json",
}


def write_reports(result: AuditResult, output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    paths = {key: output / filename for key, filename in OUTPUT_FILENAMES.items()}
    paths["estate"].write_text(_estate_markdown(result), encoding="utf-8")
    _write_json(paths["architecture"], _architecture_map(result))
    _write_json(paths["extract"], _candidate_document("extract", result.extract_candidates))
    _write_json(paths["archive"], _candidate_document("archive", result.archive_candidates))
    _write_json(paths["delete"], _candidate_document("delete-review", result.delete_candidates))
    _write_json(
        paths["pivots"],
        {
            "schema_version": "1.0",
            "reasoning_mode": "deterministic",
            "llm_hook": None,
            "suggestions": result.pivot_suggestions,
        },
    )
    return [paths[key] for key in OUTPUT_FILENAMES]


def _architecture_map(result: AuditResult) -> dict[str, Any]:
    roles = Counter(record.role or "unknown" for record in result.files)
    extensions = Counter(record.extension or "[none]" for record in result.files)
    return {
        "schema_version": "1.0",
        "scan_mode": "deterministic-read-only",
        "target_name": result.target.name,
        "summary": {
            "files_observed": len(result.files),
            "filesystem_files": sum(record.source == "filesystem" for record in result.files),
            "zip_members": sum(record.source == "zip" for record in result.files),
            "projects": len(result.projects),
            "archives": len(result.archives),
            "ignored_entries": len(result.ignored),
            "warnings": len(result.warnings),
        },
        "projects": [asdict(project) for project in result.projects],
        "file_roles": dict(sorted(roles.items())),
        "extensions": dict(sorted(extensions.items())),
        "archives": result.archives,
        "duplicate_groups": result.duplicate_groups,
        "sampled_high_signal_files": result.samples,
        "warnings": result.warnings,
        "reasoning": {
            "mode": "deterministic",
            "llm_hook": None,
            "note": "A future reasoning provider may consume this map; no model is called in v0.1.",
        },
    }


def _estate_markdown(result: AuditResult) -> str:
    categories = Counter(project.appraisal_category for project in result.projects)
    lines = [
        "# Relic Auditor Estate Report",
        "",
        "> Deterministic, read-only appraisal. No scanned file was executed, installed, changed, or deleted.",
        "",
        "## Executive inventory",
        "",
        f"- Target: `{result.target.name}`",
        f"- Files observed: **{len(result.files):,}**",
        f"- Project roots detected: **{len(result.projects):,}**",
        f"- ZIP archives inspected virtually: **{len(result.archives):,}**",
        f"- Duplicate groups: **{len(result.duplicate_groups):,}**",
        f"- Ignored generated/junk entries: **{len(result.ignored):,}**",
        "",
        "## Appraisal",
        "",
    ]
    if categories:
        for category, count in sorted(categories.items()):
            lines.append(f"- {category}: **{count}**")
    else:
        lines.append("- No project manifests or framework roots were detected.")

    lines.extend(["", "## Detected projects", ""])
    if result.projects:
        lines.extend(
            [
                "| Root | Types | Score | Category | Evidence |",
                "|---|---|---:|---|---|",
            ]
        )
        for project in result.projects:
            evidence = "; ".join(project.appraisal_reasons)
            lines.append(
                f"| `{_md(project.root)}` | {_md(', '.join(project.kinds))} | "
                f"{project.appraisal_score}/100 | {_md(project.appraisal_category)} | {_md(evidence)} |"
            )
    else:
        lines.append("No deterministic project roots found.")

    lines.extend(["", "## Candidate summary", ""])
    lines.extend(
        [
            f"- Extract candidates: **{len(result.extract_candidates)}**",
            f"- Archive candidates: **{len(result.archive_candidates)}**",
            f"- Delete-review candidates: **{len(result.delete_candidates)}**",
            "",
            "Delete candidates are recommendations for human review only. Relic Auditor never deletes them.",
            "",
            "## Pivot suggestions",
            "",
        ]
    )
    for suggestion in result.pivot_suggestions:
        lines.extend(
            [
                f"### {suggestion['title']}",
                "",
                str(suggestion["idea"]),
                "",
                f"Evidence: {', '.join(suggestion['evidence'])}. "
                f"Confidence: **{suggestion['confidence']}**.",
                "",
            ]
        )

    lines.extend(["## Safety and limitations", ""])
    lines.extend(
        [
            "- ZIPs are validated for traversal paths, absolute paths, symlinks, encryption, size, member count, and suspicious compression ratios.",
            "- ZIP contents are read as virtual members; they are not written over the target.",
            "- Generated dependencies and caches such as `node_modules`, `.git`, virtual environments, and build outputs are skipped.",
            "- High-signal previews are bounded and common secret formats are redacted.",
            "- Appraisal and pivot rules are heuristic evidence, not instructions to destroy data.",
            "- LLM reasoning is intentionally disabled in this release.",
            "",
            "## Output files",
            "",
        ]
    )
    for filename in OUTPUT_FILENAMES.values():
        lines.append(f"- `{filename}`")
    if result.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {_md(warning)}" for warning in result.warnings)
    lines.append("")
    return "\n".join(lines)


def _candidate_document(kind: str, candidates: list[Candidate]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "kind": kind,
        "advisory_only": True,
        "candidates": [asdict(candidate) for candidate in candidates],
    }


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
