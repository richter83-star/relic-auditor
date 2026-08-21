from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..safety import redact_secrets, redact_structure
from .schemas import ResurrectionResult


def write_resurrection_reports(
    result: ResurrectionResult, output_dir: Path
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    json_path = output_dir / "resurrection-plan.json"
    data = redact_structure(asdict(result))
    json_path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    paths["json"] = json_path

    md_path = output_dir / "resurrection-plan.md"
    md_path.write_text(render_resurrection_markdown(result), encoding="utf-8")
    paths["markdown"] = md_path
    return paths


def render_resurrection_markdown(result: ResurrectionResult) -> str:
    verdict_badge = (
        "🟢 **RESURRECT**" if result.verdict == "RESURRECT" else "🔴 **TOSS IT**"
    )
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
        lines.extend(
            [
                f"- **Largest Connected Core**: {len(largest.nodes)} substantive symbols across {len(largest.substantive_paths)} files",
                f"- **Surface Anchors (Entry Points)**: {len(largest.surface_anchors)}",
                f"- **Integrity Ratio**: `{largest.integrity_ratio:.2f}`",
            ]
        )

    lines.extend(["", "---", "", "## 2. Resurrection Blueprint"])

    if result.blueprint and result.verdict == "RESURRECT":
        lines.append("### Salvageable Core Source Files")
        for path in result.blueprint.salvageable_core_paths:
            lines.append(f"- `[KEEP]` `{path}`")

        if result.blueprint.cut_list:
            lines.extend(["", "### Cut List (Dead Stubs / Mocks to Discard)"])
            for item in result.blueprint.cut_list:
                lines.append(f"- `[CUT]` `{item}`")

        if result.blueprint.missing_bridge_components:
            lines.extend(["", "### Missing Bridges & Gaps"])
            for item in result.blueprint.missing_bridge_components:
                lines.append(f"- ⚠️ {item}")

        if result.blueprint.remediation_steps:
            lines.extend(["", "### Remediation Steps"])
            for step in result.blueprint.remediation_steps:
                lines.append(f"- {step}")
    else:
        lines.extend(
            [
                "No salvageable product blueprint generated.",
                f"**Reason**: {result.gate.explanation}",
            ]
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 3. Market Context & Commercial Feasibility",
            "> [!NOTE]",
            "> **Epistemic Notice**: Market context is segregated from deterministic AST code proof. Check the status below before relying on it. `offline_heuristic` means bundled static heuristics, not live research.",
        ]
    )

    if result.market_context:
        market = result.market_context
        lines.extend(
            [
                f"- **Target Market Category**: `{market.target_category}`",
                f"- **Market Intelligence Status**: `{market.status}`",
                f"- **Epistemic Rating**: `{market.epistemic_rating}`",
                "",
                "### Competitor Heuristics",
            ]
        )
        for competitor in market.active_competitors:
            lines.append(f"- **{competitor['name']}**: {competitor['model']}")

        lines.extend(["", "### Pricing & Packaging Heuristics"])
        for benchmark in market.pricing_benchmarks:
            lines.append(f"- {benchmark}")

        lines.extend(["", "### Demand Heuristics"])
        for signal in market.demand_signals:
            lines.append(f"- {signal}")

        lines.extend(["", "### Commercial & Market Risks"])
        for risk in market.market_risks:
            lines.append(f"- ⚠️ {risk}")

        if market.sources:
            lines.extend(["", "### Market Context Sources"])
            for source in market.sources:
                lines.append(f"- {source}")
    else:
        lines.append("- *Market context was omitted or unavailable for this audit.*")

    lines.extend(
        [
            "",
            "---",
            "",
            "## 4. Epistemic Audit & Limitations",
            f"- **Citation Verification**: `{'PASSED' if (result.citation_verification and result.citation_verification.valid) else 'FAILED / UNVERIFIED'}`",
        ]
    )
    for limitation in result.limitations:
        lines.append(f"- *{limitation}*")

    lines.append("")
    return redact_secrets("\n".join(lines))


def format_resurrection_console(result: ResurrectionResult) -> str:
    badge = "[RESURRECT]" if result.verdict == "RESURRECT" else "[TOSS IT]"
    lines = [
        "=== RELIC AUDITOR: RESURRECTION MODE ===",
        f"Verdict: {badge} (Confidence: {result.verdict_confidence:.0%})",
        f"Rationale: {result.verdict_rationale}",
    ]
    if result.blueprint and result.verdict == "RESURRECT":
        lines.append(
            f"Salvageable Core Paths ({len(result.blueprint.salvageable_core_paths)}):"
        )
        for path in result.blueprint.salvageable_core_paths[:5]:
            lines.append(f"  + {path}")
        if len(result.blueprint.salvageable_core_paths) > 5:
            lines.append(
                f"  ... and {len(result.blueprint.salvageable_core_paths) - 5} more"
            )

    if result.market_context:
        lines.append(f"Market Context Status: {result.market_context.status}")
        lines.append(f"Market Category: {result.market_context.target_category}")
        lines.append(
            "Competitor Heuristics: "
            + ", ".join(
                competitor["name"]
                for competitor in result.market_context.active_competitors[:3]
            )
        )
    return redact_secrets("\n".join(lines))
