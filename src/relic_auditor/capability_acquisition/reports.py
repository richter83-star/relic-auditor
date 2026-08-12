from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from ..safety import redact_secrets, redact_structure
from .schemas import AcquisitionResult


OUTPUT_FILENAMES = {
    "report": "capability_acquisition_report.md",
    "inventory": "capability_acquisition_inventory.json",
    "candidates": "capability_acquisition_candidates.json",
    "gaps": "capability_acquisition_gaps.json",
}


def write_acquisition_reports(result: AcquisitionResult, output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    paths = {key: output / value for key, value in OUTPUT_FILENAMES.items()}
    paths["report"].write_text(redact_secrets(_markdown(result)), encoding="utf-8")
    _write_json(
        paths["inventory"],
        {
            "schema_version": "1.0",
            "mode": "deterministic-local-read-only",
            "target_name": result.target.name,
            "scan_summary": result.scan_summary,
            "capabilities": result.capability_summary,
            "items": [asdict(item) for item in result.items],
        },
    )
    _write_json(
        paths["candidates"],
        {
            "schema_version": "1.0",
            "advisory_only": True,
            "candidates": result.best_candidates,
        },
    )
    _write_json(
        paths["gaps"],
        {
            "schema_version": "1.0",
            "missing_pieces": result.missing_pieces,
            "suggested_build_path": result.suggested_build_path,
            "risk_notes": result.risk_notes,
        },
    )
    return [paths[key] for key in OUTPUT_FILENAMES]


def _markdown(result: AcquisitionResult) -> str:
    lines = [
        "# Relic Auditor Capability Acquisition Report",
        "",
        "> Deterministic, local, read-only evidence analysis. No source was executed, installed, changed, extracted onto the target, deleted, or deployed.",
        "",
        "## Acquisition summary",
        "",
        f"- Target: `{_md(result.target.name)}`",
        f"- Items observed: **{result.scan_summary['files_observed']:,}**",
        f"- Items inspected as text: **{result.scan_summary['items_with_text_inspected']:,}**",
        f"- Items with matches: **{result.scan_summary['items_with_capability_matches']:,}**",
        f"- Unsafe ZIP members rejected: **{result.scan_summary['unsafe_archive_members']:,}**",
        "- LLM influence on deterministic findings: **none**",
        "",
        "## Capability coverage",
        "",
        "| Capability | Status | Confidence | Candidates | Best evidence |",
        "|---|---|---:|---:|---|",
    ]
    for row in result.capability_summary:
        paths = ", ".join(f"`{_md(path)}`" for path in row["best_paths"]) or "—"
        lines.append(
            f"| {_md(str(row['title']))} | {_md(str(row['status']))} | "
            f"{float(row['confidence']):.2f} | {row['candidate_count']} | {paths} |"
        )
    lines.extend(["", "## Best reusable candidates", ""])
    if result.best_candidates:
        lines.extend(
            [
                "| Rank | Capability | Path | Confidence | Context | Reusable |",
                "|---:|---|---|---:|---|---|",
            ]
        )
        for candidate in result.best_candidates[:20]:
            lines.append(
                f"| {candidate['rank']} | {_md(str(candidate['title']))} | "
                f"`{_md(str(candidate['path']))}` | {float(candidate['confidence']):.2f} | "
                f"{_md(str(candidate['context']))} | "
                f"{'yes' if candidate['reusable'] else 'validate'} |"
            )
    else:
        lines.append("No candidate crossed the minimum evidence threshold.")
    lines.extend(["", "## Missing or weak pieces", ""])
    if result.missing_pieces:
        for item in result.missing_pieces:
            lines.append(
                f"- **{_md(str(item['title']))}** — {item['status']} "
                f"({float(item['confidence']):.2f}). {_md(str(item['reason']))}"
            )
    else:
        lines.append("- All requested capability categories have at least candidate-level evidence.")
    lines.extend(["", "## Suggested build path", ""])
    for step in result.suggested_build_path:
        lines.extend(
            [
                f"### {step['sequence']}. {_md(str(step['title']))}",
                "",
                f"Disposition: **{_md(str(step['disposition']))}**. {_md(str(step['rationale']))}",
                "",
                f"Acceptance gate: {_md(str(step['acceptance_gate']))}",
                "",
            ]
        )
    lines.extend(["## Risk notes", ""])
    lines.extend(f"- {_md(note)}" for note in result.risk_notes)
    lines.extend(
        [
            "",
            "## Safety contract",
            "",
            "- ZIPs are inspected virtually with traversal, absolute-path, symlink, encryption, expansion-size, member-count, and compression-ratio checks.",
            "- Generated dependencies, caches, VCS metadata, and known junk are skipped.",
            "- Evidence excerpts and every JSON/Markdown report are secret-redacted.",
            "- Matches are static evidence, not proof that a capability is correct, reachable, secure, or production-ready.",
            "- Relic proposes a build order only. It never connects components or expands system authority.",
            "",
            "## Output files",
            "",
        ]
    )
    lines.extend(f"- `{name}`" for name in OUTPUT_FILENAMES.values())
    lines.append("")
    return "\n".join(lines)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(redact_structure(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _md(value: str) -> str:
    return redact_secrets(value).replace("|", "\\|").replace("\n", " ")
