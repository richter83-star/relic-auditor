from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .schemas import DiscoveryResult


@dataclass(frozen=True)
class CompatibleOpportunities:
    opportunities: tuple[dict[str, Any], ...]
    source_schema: str
    requires_rescan_for_assets: bool
    warnings: tuple[str, ...] = ()


def _stable_id(title: str, evidence: list[str]) -> str:
    payload = json.dumps([title, sorted(evidence)], separators=(",", ":"))
    return "opp_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def normalize_opportunity(
    raw: Mapping[str, Any], evidence_index: Mapping[str, Mapping[str, Any]] | None = None
) -> dict[str, Any]:
    item = copy.deepcopy(dict(raw))
    evidence = sorted({str(value) for value in item.get("evidence", []) if value})
    item["opportunity_id"] = str(
        item.get("opportunity_id") or _stable_id(str(item.get("title", "Untitled")), evidence)
    )
    item["title"] = str(item.get("title") or "Untitled opportunity")
    # Preserve the established opportunity-object schema while the report
    # envelope advances independently. Older consumers asserted this field.
    item["schema_version"] = str(item.get("schema_version") or "1.0")
    item["canonical_loader_version"] = "0.9"

    indexed = evidence_index or {}
    assets = item.get("reusable_assets")
    if not isinstance(assets, list):
        reuse = item.get("extraction_plan", {}).get("reuse", [])
        assets = []
        for path in sorted({str(value) for value in reuse if value}):
            refs = [
                ref
                for ref in evidence
                if str(indexed.get(ref, {}).get("path", "")) == path
            ]
            assets.append(
                {
                    "path": path,
                    "sha256": None,
                    "evidence": refs,
                    "claim": "Observed candidate; reuse requires hash and provenance review.",
                }
            )
    normalized_assets = []
    for asset in assets:
        if not isinstance(asset, Mapping) or not asset.get("path"):
            continue
        normalized_assets.append(
            {
                "path": str(asset["path"]),
                "sha256": str(asset["sha256"]) if asset.get("sha256") else None,
                "evidence": sorted(
                    {str(value) for value in asset.get("evidence", []) if value}
                ),
                "claim": str(
                    asset.get("claim")
                    or "Observed candidate; ownership and fitness are not proven."
                ),
            }
        )
    item["reusable_assets"] = sorted(
        normalized_assets, key=lambda value: value["path"].casefold()
    )

    missing = item.get("missing_components")
    if not isinstance(missing, list):
        plan = item.get("extraction_plan", {})
        missing = [
            *plan.get("missing_interfaces", []),
            *plan.get("missing_tests", []),
            *plan.get("deployment_work", []),
        ]
    item["missing_components"] = sorted({str(value) for value in missing if value})

    status = str(item.get("technical_verification_status", "not_performed"))
    score = int(item.get("evidence_score") or 0)
    if status == "high" and len(evidence) >= 2:
        strength = "verified"
    elif score >= 50 and len(evidence) >= 2:
        strength = "supported"
    else:
        strength = "exploratory"
    item["evidence_strength"] = strength
    item["build_pack_readiness"] = (
        "eligible" if strength in {"verified", "supported"} and item["reusable_assets"] else "review_required"
    )
    item["evidence"] = evidence
    return item


def load_opportunities(source: Path | Mapping[str, Any] | DiscoveryResult) -> CompatibleOpportunities:
    if isinstance(source, DiscoveryResult):
        raw = {
            "schema_version": "0.9",
            "opportunities": source.opportunities,
            "evidence": source.evidence_index,
        }
    elif isinstance(source, Path):
        raw = json.loads(source.read_text(encoding="utf-8"))
    else:
        raw = copy.deepcopy(dict(source))

    if isinstance(raw, list):
        raw = {"schema_version": "legacy", "opportunities": raw}
    opportunities = raw.get("opportunities", [])
    if not isinstance(opportunities, list):
        raise ValueError("opportunity report must contain an opportunities list")
    evidence_items = raw.get("evidence", raw.get("evidence_index", []))
    evidence_index = {
        str(item.get("evidence_id")): item
        for item in evidence_items
        if isinstance(item, Mapping) and item.get("evidence_id")
    }
    normalized = tuple(
        normalize_opportunity(item, evidence_index)
        for item in opportunities
        if isinstance(item, Mapping)
    )
    source_schema = str(raw.get("schema_version", "legacy"))
    rescan = any(
        asset.get("sha256") is None
        for opportunity in normalized
        for asset in opportunity["reusable_assets"]
    )
    warnings = (
        ("Historical report lacks hashes required for safe asset export.",)
        if rescan
        else ()
    )
    return CompatibleOpportunities(normalized, source_schema, rescan, warnings)
