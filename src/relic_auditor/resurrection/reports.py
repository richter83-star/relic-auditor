from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..safety import redact_secrets
from .schemas import ResurrectionResult


def write_resurrection_reports(result: ResurrectionResult, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {}

    # 1. JSON Report
    json_path = output_dir / "resurrection-plan.json"
    data = asdict(result)
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    paths["json"] = json_path

    # 2. Markdown Report
    md_path = output_dir / "resurrection-plan.md"
    md_content = render_resurrection_markdown(result)
    md_path.write_text(md_content, encoding="utf-8")
    paths["markdown"] = md_path

    return paths


def render_resurrection_markdown(result: ResurrectionResult) -> str:
    verdict_badge = "🟢 **RESURRECT**" if result.verdict == "RESURRECT" else "🔴 **TOSS IT**"
    lines = [
        "# Relic Auditor — Resurrection Plan",
        "",
        f"### Verdict: {verdict_badge} (Confidence: {result.verdict_confidence:.0%})",
        "",
        f"> **Assessment**: {result.verdict_rationale}",
        "",
        "---",
        "",
        "## 1. Deterministic Proof (Ground Truth)",
        f"- **Gate Status**: `{result.gate.verdict}` (`{result.gate.reason}`)",
        f"- **Substantive Subgraphs Found**: {len(result.subgraphs)}",
    ]

    if result.subgraphs:
        largest = result.subgraphs[0]
        lines.extend([
            f"- **Largest Connected Core**: {len(largest.nodes)} substantive symbols across {len(largest.substantive_paths)} files",
            f"- **Surface Anchors (Entry Points)**: {len(largest.surface_anchors)}",
            f"- **Integrity Ratio**: `{largest.integrity_ratio:.2f}`",
        ])

    lines.extend([
        "",
        "---",
        "",
        "## 2. Resurrection Blueprint",
    ])

    if result.blueprint and result.verdict == "RESURRECT":
        lines.extend([
            "### Salvageable Core Source Files",
        ])
        for p in result.blueprint.salvageable_core_paths:
            lines.append(f"- `[KEEP]` `{p}`")

        if result.blueprint.cut_list:
            lines.extend(["", "### Cut List (Dead Stubs / Mocks to Discard)"])
            for c in result.blueprint.cut_list:
                lines.append(f"- `[CUT]` `{c}`")

        if result.blueprint.missing_bridge_components:
            lines.extend(["", "### Missing Bridges & Gaps"])
            for m in result.blueprint.missing_bridge_components:
                lines.append(f"- ⚠️ {m}")

        if result.blueprint.remediation_steps:
            lines.extend(["", "### Remediation Steps"])
            for step in result.blueprint.remediation_steps:
                lines.append(f"- {step}")
    else:
        lines.extend([
            "No salvageable product blueprint generated.",
            f"**Reason**: {result.gate.explanation}",
        ])

    lines.extend([
        "",
        "---",
        "",
        "## 3. Real-Time Market Context & Commercial Feasibility",
        "> [!NOTE]",
        "> **Epistemic Notice**: Market data is external commercial speculation. It contextualizes market demand but is strictly segregated from deterministic AST code proof.",
    ])

    if result.market_context:
        mc = result.market_context
        lines.extend([
            f"- **Target Market Category**: `{mc.target_category}`",
            f"- **Market Intelligence Status**: `{mc.status}`",
            "",
            "### Known Competitor Landscape & Models",
        ])
        for comp in mc.active_competitors:
            lines.append(f"- **{comp['name']}**: {comp['model']}")

        lines.extend(["", "### Pricing & Packaging Benchmarks"])
        for pr in mc.pricing_benchmarks:
            lines.append(f"- {pr}")

        lines.extend(["", "### Market Signals & Demand"])
        for ds in mc.demand_signals:
            lines.append(f"- {ds}")

        lines.extend(["", "### Commercial & Market Risks"])
        for mr in mc.market_risks:
            lines.append(f"- ⚠️ {mr}")
    else:
        lines.append("- *Market intelligence was omitted or unavailable for this audit.*")

    lines.extend([
        "",
        "---",
        "",
        "## 4. Epistemic Audit & Limitations",
        f"- **Citation Verification**: `{'PASSED' if (result.citation_verification and result.citation_verification.valid) else 'FAILED / UNVERIFIED'}`",
    ])
    for lim in result.limitations:
        lines.append(f"- *{lim}*")

    lines.append("")
    return redact_secrets("\n".join(lines))


def format_resurrection_console(result: ResurrectionResult) -> str:
    badge = "[RESURRECT]" if result.verdict == "RESURRECT" else "[TOSS IT]"
    lines = [
        f"=== RELIC AUDITOR: RESURRECTION MODE ===",
        f"Verdict: {badge} (Confidence: {result.verdict_confidence:.0%})",
        f"Rationale: {result.verdict_rationale}",
    ]
    if result.blueprint and result.verdict == "RESURRECT":
        lines.append(f"Salvageable Core Paths ({len(result.blueprint.salvageable_core_paths)}):")
        for p in result.blueprint.salvageable_core_paths[:5]:
            lines.append(f"  + {p}")
        if len(result.blueprint.salvageable_core_paths) > 5:
            lines.append(f"  ... and {len(result.blueprint.salvageable_core_paths) - 5} more")

    if result.market_context:
        lines.append(f"Market Category: {result.market_context.target_category}")
        lines.append(f"Competitor Signals: {', '.join(c['name'] for c in result.market_context.active_competitors[:3])}")
    return "\n".join(lines)

