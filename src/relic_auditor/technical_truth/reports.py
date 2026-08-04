from __future__ import annotations

import json
from pathlib import Path

from .schemas import MIN_CONCLUSION_COVERAGE, TechnicalTruthResult
from ..safety import redact_secrets, redact_structure


TECHNICAL_OUTPUTS = {
    "summary": "technical_truth_summary.json",
    "symbols": "symbol_inventory.json",
    "graph": "relationship_graph.json",
    "families": "project_families.json",
    "surfaces": "application_surfaces.json",
    "workflows": "workflow_inventory.json",
    "capabilities": "capability_verification.json",
    "contradictions": "contradictions.json",
    "reachability": "reachability_report.json",
    "report": "technical_truth_report.md",
}


def write_technical_truth_reports(result: TechnicalTruthResult, output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    paths = {key: output / value for key, value in TECHNICAL_OUTPUTS.items()}
    _json(paths["summary"], result.summary)
    _json(paths["symbols"], {"schema_version": "1.0", "symbols": result.symbols, "parse_results": result.parse_results})
    _json(paths["graph"], result.graph)
    _json(paths["families"], {"schema_version": "1.0", "project_families": result.project_families})
    _json(paths["surfaces"], {"schema_version": "1.0", **result.surfaces})
    _json(paths["workflows"], {"schema_version": "1.0", "workflows": result.workflows})
    _json(paths["capabilities"], {"schema_version": "1.0", "capabilities": result.capabilities})
    _json(paths["contradictions"], {"schema_version": "1.0", "contradictions": result.contradictions})
    _json(paths["reachability"], {"schema_version": "1.0", "symbols": result.reachability})
    paths["report"].write_text(redact_secrets(_report(result)), encoding="utf-8")
    return [paths[key] for key in TECHNICAL_OUTPUTS]


def _report(result):
    s = result.summary
    verified = [w for w in result.workflows if w["completion_status"] == "verified_end_to_end"]
    broken = [w for w in result.workflows if w["completion_status"] != "verified_end_to_end"]
    disconnected = [c for c in result.capabilities if c["status"] == "implemented_but_disconnected"]
    interface = [c for c in result.capabilities if c["status"] == "interface_only"]
    schema = [c for c in result.capabilities if c["status"] == "schema_only"]
    test_only = [c for c in result.capabilities if c["status"] == "test_or_mock_only"]
    dead = [r for r in result.reachability if r["status"] in {"unreferenced", "test_only"}]
    strongest = sorted(result.capabilities, key=lambda c: (-c["confidence"], c["name"]))[:5]
    mock_surfaces = [item for item in result.surfaces.get("ui_screens", []) if item.get("mock_only")]
    mock_tests = [item for item in result.surfaces["tests"] if item["kind"] == "mock"]
    lines = ["# Relic Technical Truth Report", "", "> Static analysis only. Scanned source was not imported, executed, built, tested, migrated, or modified.", "",
             "## Executive technical conclusion", "", _executive_conclusion(result), "", _evidence_gate_notice(result), "", f"Relic parsed **{s['files_parsed']}** files, detected **{s['symbols_detected']}** symbols and **{s['relationships_detected']}** relationships, reconstructed **{s['workflows_detected']}** workflows, and verified **{s['verified_workflows']}** end-to-end workflows.", "",
             "## What the software claims to do", "", f"Documentation/code contradictions detected: **{s['contradictions_detected']}**.", "",
             "## Observed capability evidence", ""] + [f"- **{c['name']}** — {c['status'].replace('_', ' ')} ({c.get('evidence_strength', c['confidence_label'])} evidence)" for c in result.capabilities]
    lines += ["", "## Project-family map", ""] + [f"- `{f['canonical_hint']}`: {', '.join(f['members'])} — {f['relationship']} ({f['confidence']})" for f in result.project_families]
    lines += ["", "## Language and framework coverage", "", f"- Coverage: {s['coverage']['ratio']:.0%}", f"- Languages: {json.dumps(s['coverage']['languages'], sort_keys=True)}", "",
              "## Verified application surfaces", "", f"- Framework evidence: {', '.join(sorted({item['name'] for item in result.surfaces.get('frameworks', [])})) or 'none'}", f"- Endpoints: {len(result.surfaces['endpoints'])}", f"- UI screens: {len(result.surfaces.get('ui_screens', []))}", f"- UI actions: {len(result.surfaces['ui'])}", f"- Schemas: {len(result.surfaces['schemas'])}", f"- Async surfaces: {len(result.surfaces['async'])}", f"- Integrations: {len(result.surfaces['integrations'])}", "",
              "## Verified end-to-end workflows", ""] + _workflow_lines(verified)
    lines += ["", "## Partial or broken workflows", ""] + _workflow_lines(broken)
    lines += ["", "## Disconnected implementations", ""] + _cap_lines(disconnected)
    lines += ["", "## Interface-only features", ""] + _cap_lines(interface)
    lines += ["", "## Schema-only features", ""] + _cap_lines(schema)
    lines += ["", "## Test-only or mock-only behavior", ""]
    lines += _cap_lines(test_only) if test_only else ([] if mock_surfaces or mock_tests else ["- None."])
    lines += [f"- UI screen `{item['file']}::{item['name']}` uses mock or fixture data." for item in mock_surfaces]
    lines += [f"- `{item['file']}` contains mock-based test evidence; tests were not executed." for item in mock_tests]
    lines += ["", "## Contradictions", ""] + [f"- {c['claim']} **Finding:** {c['technical_finding']}" for c in result.contradictions]
    lines += ["", "## Dead and unreachable code", ""] + [f"- `{r['file']}::{r['name']}` — {r['status']}" for r in dead[:100]]
    lines += ["", "## Strongest reusable capabilities", ""] + _cap_lines(strongest)
    lines += ["", "## Technical extraction candidates", ""] + [f"- {c['name']}: {c['extraction_readiness']} readiness; {c['coupling']} coupling." for c in strongest]
    missing = sorted({m for c in result.capabilities for m in c["missing_components"]})
    lines += ["", "## Major missing components", ""] + ([f"- {m}" for m in missing] or ["- No critical missing component was proven."])
    lines += ["", "## Security and operational concerns", ""] + ([f"- `{r['path']}:{r['line']}` — {r['indicator']} ({r['conclusion']})" for r in result.surfaces["risk_indicators"]] or ["- No conclusive security finding was established. Static absence of a finding is not a security guarantee."])
    lines += ["", "## Unsupported or uncertain areas", ""] + [f"- {item}" for item in s["limitations"]]
    lines += ["", "## Impact on Product Resurrection recommendations", "", "Product opportunities are now gated by technical verification. Unverified or disconnected implementations cannot be described as existing launch-ready products and receive capped readiness scores.", "",
              "## Evidence appendix", ""] + [f"- `{e['edge_id']}` {e['type']}: `{e['source']}` → `{e['target']}` ({e['observation_type']}, {e['confidence']})" for e in result.graph["edges"][:200]]
    lines.append("")
    return "\n".join(lines)


def _workflow_lines(items):
    return [f"- **{w['name']}** — {w['completion_status'].replace('_', ' ')}; confidence {w['confidence_label']}. Missing: {', '.join(w['missing_links']) or 'none detected'}" for w in items] or ["- None."]
def _cap_lines(items):
    return [f"- **{c['name']}** — {c['status'].replace('_', ' ')}. {c['explanation']}" for c in items] or ["- None."]


def _executive_conclusion(result):
    gate = result.summary.get("conclusion_gate", {})
    if gate.get("status") != "eligible":
        coverage = result.summary.get("coverage", {})
        considered = coverage.get("considered_files", 0)
        parsed = coverage.get("supported_files", 0)
        failures = coverage.get("parser_failures", 0)
        return (
            f"INSUFFICIENT EVIDENCE — no negative technical conclusion is stated. "
            f"Relic parsed or partially parsed {parsed} of {considered} considered "
            f"source files ({coverage.get('ratio', 0):.0%} coverage), with "
            f"{failures} internal parser failure{'s' if failures != 1 else ''}. "
            f"The evidence gate requires at least {MIN_CONCLUSION_COVERAGE:.0%} "
            "coverage and no unparsed or unsupported source. Inspect "
            "`symbol_inventory.json` → `parse_results` before relying on absence, "
            "missing-component, or contradiction findings."
        )
    by_key = {item["key"]: item for item in result.capabilities}
    verified = [item for item in result.workflows if item["completion_status"] == "verified_end_to_end"]
    parts = []
    if verified:
        parts.append(f"Static evidence verifies {len(verified)} connected end-to-end workflow{'s' if len(verified) != 1 else ''}.")
    elif result.contradictions:
        parts.append("This repository is not verified as the complete product described by its documentation.")
    else:
        parts.append("No end-to-end product workflow was statically verified.")
    auth = by_key.get("authenticated-access")
    ingestion = by_key.get("document-ingestion")
    evaluation = by_key.get("rule-evaluation")
    reporting = by_key.get("report-generation")
    billing = by_key.get("subscription-billing")
    if auth and ingestion and auth["status"] in {"partially_implemented", "verified_end_to_end"} and ingestion["status"] in {"partially_implemented", "verified_end_to_end"}:
        parts.append("The strongest connected evidence is an authenticated document-ingestion prototype.")
    if evaluation and evaluation["status"] != "verified_end_to_end":
        parts.append(f"Rule evaluation is {evaluation['status'].replace('_', ' ')}.")
    broken_queue = any(any("no matching production consumer" in link.lower() for link in item["missing_links"]) for item in result.workflows)
    if broken_queue:
        parts.append("The analysis path stops after queue production because no matching production consumer is connected.")
    if reporting and reporting["status"] != "verified_end_to_end":
        parts.append(f"Reporting is {reporting['status'].replace('_', ' ')}.")
    if any(item.get("mock_only") for item in result.surfaces.get("ui_screens", [])):
        parts.append("At least one user-visible screen renders mock data.")
    if billing and billing["status"] in {"configuration_only", "contradicted"}:
        parts.append("Billing is configured or mentioned but not implemented as a verified production workflow.")
    return " ".join(parts)


def _evidence_gate_notice(result):
    gate = result.summary.get("conclusion_gate", {})
    if gate.get("status") == "eligible":
        return (
            "> Evidence gate passed. Negative conclusions remain limited to the "
            "specific project families and static evidence cited below."
        )
    reasons = ", ".join(gate.get("blocking_reasons", [])) or "unknown"
    return (
        "> Evidence gate blocked negative conclusions. Positive observations below "
        "remain usable, but absence and contradiction findings are not an appraisal "
        f"of the complete estate. Blocking reasons: {reasons}."
    )


def _json(path, data):
    path.write_text(
        json.dumps(redact_structure(data), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
