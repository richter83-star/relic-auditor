from __future__ import annotations

import json
from pathlib import Path

from .schemas import DiscoveryResult
from ..safety import redact_secrets, redact_structure


PRODUCT_OUTPUTS = {
    "opportunities": "product_opportunities.json",
    "brief": "product_resurrection_brief.md",
    "gtm": "gtm_proposals.md",
    "capabilities": "capability_inventory.json",
    "evidence": "opportunity_evidence.json",
    "extraction": "extraction_plans.json",
    "market": "market_validation.json",
}


def write_product_reports(result: DiscoveryResult, output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    paths = {key: output / name for key, name in PRODUCT_OUTPUTS.items()}
    _json(paths["opportunities"], {"schema_version": "0.9", "opportunities": result.opportunities, "rejected_candidates": result.rejected_candidates})
    _json(paths["capabilities"], {"schema_version": "1.0", "intent_reconstruction": result.intent, "project_families": result.project_families, "capabilities": result.capabilities})
    _json(paths["evidence"], {"schema_version": "1.0", "evidence": result.evidence_index})
    _json(paths["extraction"], {"schema_version": "1.0", "plans": result.extraction_plans})
    _json(paths["market"], result.market_validation)
    paths["brief"].write_text(redact_secrets(_brief(result)), encoding="utf-8")
    paths["gtm"].write_text(redact_secrets(_gtm(result)), encoding="utf-8")
    return [paths[key] for key in PRODUCT_OUTPUTS]


def _brief(result: DiscoveryResult) -> str:
    opportunities = result.opportunities
    top = opportunities[0] if opportunities else None
    revenue = next((o for o in opportunities if "Highest probability of near-term revenue" in o["rank_labels"]), top)
    surprising = next((o for o in opportunities if "Most surprising hidden product" in o["rank_labels"]), top)
    lines = [
        "# Relic Product Resurrection Brief", "",
        "> Offline, repository-derived hypothesis. No market validation or source execution was performed.", "",
        "## Executive summary", "",
        f"Relic found **{len(result.capabilities)}** evidenced capabilities and **{len(opportunities)}** proposals that passed the quality gate.",
        "" ,"## What the estate was intended to become", "",
        f"**{result.intent['apparent_original_product']}** — {result.intent['intended_workflow']}", "",
        "## What it actually contains", "", result.intent["actual_implementation_state"], "",
        "## Most valuable reusable capabilities", "",
    ]
    lines += [f"- **{c['name']}** — {c['description']} ({c['completion_level']}% completion signal)" for c in result.capabilities[:8]]
    lines += ["", "## Hidden products discovered", ""]
    if opportunities:
        lines += ["| Rank | Product | Score | Evidence | Effort | Why it may fail |", "|---:|---|---:|---:|---|---|"]
        for index, o in enumerate(opportunities, 1):
            lines.append(f"| {index} | {o['title']} | {o['overall_score']} | {o['evidence_score']} | {o['extraction_effort']} | {o['reject_reason']} |")
    else:
        lines.append("No proposal passed the evidence quality gate.")
    for heading, item in (("Recommended primary product", top), ("Recommended near-term revenue product", revenue), ("Most surprising product opportunity", surprising)):
        lines += ["", f"## {heading}", ""]
        lines.append(f"**{item['title']}** — {item['summary']}" if item else "No supported recommendation.")
    if top:
        lines += ["", "## Extraction plan", "", f"- Reuse: {', '.join(top['extraction_plan']['reuse'])}", f"- Rewrite: {', '.join(top['extraction_plan']['rewrite'])}", f"- Relative effort: **{top['extraction_effort']}**",
                  "", "## GTM plan", "", top["gtm"]["positioning"],
                  "", "## 30-day validation plan", "", f"- Experiments: {', '.join(top['gtm']['validation_30_day']['experiments'])}", f"- Success: {top['gtm']['validation_30_day']['success']}", f"- Kill: {top['gtm']['validation_30_day']['kill']}", f"- Pivot: {top['gtm']['validation_30_day']['pivot']}",
                  "", "## Risks and counterarguments", ""] + [f"- {risk}" for risk in top["risks"]]
        lines += ["", "## What should not be built", "", "- Do not complete unrelated flagship scope before a buyer validates the narrow workflow.", "- Do not add a marketplace, autonomous agent layer, or broad dashboard without repository and customer evidence.",
                  "", "## Unknowns requiring human confirmation", ""] + [f"- {u}" for u in top["unknowns"]]
    lines += ["", "## Repository evidence appendix", ""]
    lines += [f"- `{e['evidence_id']}` — `{e['path']}` lines {e['lines']} ({e['evidence_type']}, confidence {e['confidence']})" for e in result.evidence_index]
    lines.append("")
    return "\n".join(lines)


def _gtm(result: DiscoveryResult) -> str:
    lines = ["# Relic GTM Proposals", "", "> Pricing and market claims are hypotheses until externally validated.", ""]
    for o in result.opportunities:
        sales, validation = o["gtm"]["sales_assets"], o["gtm"]["validation_30_day"]
        lines += [f"## {o['title']}", "", o["gtm"]["positioning"], "", f"**Offer:** {o['gtm']['offer_model']} — {o['gtm']['deliverable']}", "",
                  f"**Pricing hypothesis:** ${o['pricing_hypothesis']['low']} / ${o['pricing_hypothesis']['base']} / ${o['pricing_hypothesis']['high']} per {o['pricing_hypothesis']['unit']}.", "",
                  f"**Primary channel:** {o['gtm']['channels']['primary']}", "", f"### Landing page", "", sales["headline"], "", sales["subheadline"], ""] + [f"- {b}" for b in sales["benefits"]]
        lines += ["", "### Outbound email", "", "```text", sales["email"], "```", "", "### Discovery", "", sales["discovery_opening"], ""] + [f"- {q}" for q in sales["discovery_questions"]]
        lines += ["", "### Pilot and validation", "", sales["pilot_offer"], "", f"- Success: {validation['success']}", f"- Warning: {validation['warning']}", f"- Kill: {validation['kill']}", f"- Pivot: {validation['pivot']}", ""]
    return "\n".join(lines)


def _json(path: Path, data) -> None:
    path.write_text(
        json.dumps(redact_structure(data), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
