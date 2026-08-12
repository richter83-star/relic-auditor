from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..models import AuditResult
from ..product_discovery.compatibility import normalize_opportunity
from .canonical import digest, stable_id
from .policy import classify_assets, scan_fingerprint
from .providers import BuildPackProvider, bounded_enrichment
from .schemas import EligibilityError, PreparedBuildPack


def _task(kind: str, title: str, detail: str, order: int) -> dict[str, Any]:
    seed = {"kind": kind, "title": title, "detail": detail, "order": order}
    return {"task_id": stable_id("task", seed, 12), **seed, "depends_on": []}


def compose_build_pack(
    opportunity: Mapping[str, Any],
    *,
    audit: AuditResult | None = None,
    source_root: Path | None = None,
    provider: BuildPackProvider | None = None,
    allow_provider: bool = False,
) -> PreparedBuildPack:
    item = normalize_opportunity(opportunity)
    if item["evidence_strength"] == "exploratory":
        raise EligibilityError(
            "Opportunity evidence is too weak for Build Pack generation"
        )
    if item.get("documentation_only"):
        raise EligibilityError("Documentation-only evidence remains exploratory")

    if audit is not None:
        root = (source_root or audit.target).expanduser().resolve()
        assets = classify_assets(audit, item, root)
        scan_hash = scan_fingerprint(audit)
        rescan_required = False
    else:
        root = None
        assets = [
            {
                "source_path": asset["path"],
                "source_sha256": asset.get("sha256"),
                "destination_path": None,
                "classification": "blocked",
                "reasons": ["A current rescan is required before asset reuse."],
                "evidence": asset.get("evidence", []),
                "claim": asset.get("claim", "Historical candidate."),
                "provenance": {
                    "source": "historical_report",
                    "ownership_proven": False,
                },
            }
            for asset in item["reusable_assets"]
        ]
        scan_hash = "historical-no-scan"
        rescan_required = True

    tasks = []
    for index, asset in enumerate(assets, 1):
        tasks.append(
            _task(
                "reuse_review",
                f"Review reusable asset {asset['source_path']}",
                "Verify provenance, license, evidence, destination, and integration fitness.",
                index,
            )
        )
    start = len(tasks) + 1
    for offset, missing in enumerate(item["missing_components"]):
        tasks.append(
            _task(
                "new_work",
                str(missing),
                "Implement and verify as new work; no reusable asset was claimed.",
                start + offset,
            )
        )

    context = {
        "opportunity_id": item["opportunity_id"],
        "title": item["title"],
        "evidence_strength": item["evidence_strength"],
        "missing_components": item["missing_components"],
    }
    enrichment = bounded_enrichment(provider, context, allowed=allow_provider)
    content = {
        "opportunity": {
            "opportunity_id": item["opportunity_id"],
            "title": item["title"],
            "summary": item.get("summary", ""),
            "target_user": item.get("target_user", "Not established"),
            "problem": item.get(
                "job_to_be_done", item.get("trigger_event", "Not established")
            ),
            "evidence_strength": item["evidence_strength"],
            "evidence": item["evidence"],
        },
        "scan": {
            "fingerprint": scan_hash,
            "rescan_required_for_assets": rescan_required,
        },
        "brief": {
            "product_concept": item.get("summary", item["title"]),
            "target_user": item.get("target_user", "Not established"),
            "problem_solved": item.get("job_to_be_done", "Not established"),
            "recommended_next_step": (
                item.get("next_validation_steps")
                or ["Validate the narrow workflow with a buyer."]
            )[0],
        },
        "scope": {
            "mvp_in": list(item.get("wedge", {}).get("required_features", [])),
            "mvp_out": list(item.get("wedge", {}).get("excluded_features", [])),
            "manual_work_allowed": item.get("wedge", {}).get(
                "manual_work_allowed", "Review remains manual."
            ),
        },
        "architecture": {
            "components": list(item.get("supporting_capability_ids", [])),
            "new_components": list(item["missing_components"]),
            "boundary": "New product workspace only; original scan target remains read-only.",
        },
        "tasks": tasks,
        "acceptance_criteria": [
            "Every implementation claim resolves to bundled evidence or is labeled new work.",
            "Approved asset hashes and manifest checksums verify.",
            "No target code is executed and the scanned source remains unchanged.",
            "Generated criteria remain unverified until a later approved build session.",
        ],
        "assets": assets,
        "provenance": {
            "opportunity_evidence": item["evidence"],
            "license_classification_is_legal_advice": False,
            "ownership_proven": False,
        },
        "risks": sorted(set(map(str, item.get("risks", []))))
        + [
            "A Build Pack is decision support, not proof the product will work or sell.",
            "Market, pricing, and GTM claims remain hypotheses until validated.",
        ],
        "decisions": [
            "Asset reuse requires explicit content-addressed approval.",
            "Builder handoffs are render-only in v0.10.0.",
        ],
        "provider_enrichment": enrichment,
        "safety": {
            "target_executed": False,
            "target_modified": False,
            "network_required": False,
            "coding_agent_launched": False,
            "os_sandbox_provided": False,
        },
    }
    content_hash = digest(content)
    return PreparedBuildPack(
        pack_id=f"bp_{content_hash[:24]}",
        content_hash=content_hash,
        content=content,
        source_root=root,
    )
