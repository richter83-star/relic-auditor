from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import PurePosixPath
from typing import Any

from ..models import AuditResult, FileRecord
from ..safety import redact_secrets
from .providers import provider_for
from .schemas import DiscoveryConfig, DiscoveryResult
from .compatibility import normalize_opportunity


GENERIC_PHRASES = (
    "ai-powered platform",
    "revolutionize the industry",
    "all-in-one solution",
    "seamless experience",
    "leverage cutting-edge technology",
    "businesses of all sizes",
)

CAPABILITY_RULES = (
    (
        "bulk-ingestion",
        "Structured data ingestion",
        ("ingest", "import", "upload", "csv", "bulk"),
        "Accepts and normalizes data or files for downstream work.",
    ),
    (
        "reporting",
        "Traceable reporting",
        ("report", "export", "pdf", "dashboard", "finding"),
        "Turns system results into a reviewable report or dashboard.",
    ),
    (
        "evaluation",
        "Scoring and evaluation",
        ("score", "evaluate", "rank", "grade", "assessment"),
        "Applies repeatable evaluation or scoring to inputs.",
    ),
    (
        "workflow",
        "Workflow orchestration",
        ("workflow", "pipeline", "queue", "job", "orchestrat", "agent"),
        "Coordinates multi-step or asynchronous work.",
    ),
    (
        "security",
        "Security analysis",
        ("security", "vulnerability", "suricata", "ghidra", "threat", "scan"),
        "Analyzes systems or artifacts for security-relevant findings.",
    ),
    (
        "compliance",
        "Compliance gap analysis",
        ("compliance", "policy", "regulation", "control", "audit"),
        "Compares evidence or policies against defined requirements.",
    ),
    (
        "developer-cli",
        "Operator command-line workflow",
        ("argparse", "click.command", "typer", "commander", "console_scripts"),
        "Provides a repeatable local operator workflow.",
    ),
    (
        "authentication",
        "User access control",
        ("login", "signup", "jwt", "oauth", "authentication"),
        "Identifies users and controls access.",
    ),
    (
        "billing",
        "Commercial billing",
        ("stripe", "subscription", "checkout", "invoice", "billing"),
        "Supports payment, subscription, or invoice workflows.",
    ),
    (
        "notification",
        "Operational notification",
        ("email", "notification", "webhook", "slack"),
        "Delivers status or results to another person or system.",
    ),
)


def discover_products(
    audit: AuditResult, config: DiscoveryConfig | None = None, technical_truth=None
) -> DiscoveryResult:
    cfg = config or DiscoveryConfig()
    evidence = _evidence_index(audit, cfg.maximum_sampled_source_size)
    intent = _reconstruct_intent(audit, evidence)
    capabilities = _capabilities(audit, evidence)
    families = _project_families(audit)
    candidates = _opportunity_candidates(audit, intent, capabilities, families, cfg)
    _apply_technical_gate(candidates, technical_truth)
    accepted, rejected = _quality_gate(candidates, cfg.minimum_evidence_score)
    accepted.sort(key=lambda item: (-item["overall_score"], item["opportunity_id"]))
    accepted = accepted[: cfg.max_opportunities]
    evidence_by_id = {item["evidence_id"]: item for item in evidence}
    records_by_path = {record.path: record for record in audit.files}
    for index, opportunity in enumerate(accepted):
        reusable_assets = []
        for path in opportunity["extraction_plan"]["reuse"]:
            record = records_by_path.get(path)
            refs = sorted(
                evidence_id
                for evidence_id in opportunity["evidence"]
                if evidence_by_id.get(evidence_id, {}).get("path") == path
            )
            reusable_assets.append(
                {
                    "path": path,
                    "sha256": record.sha256 if record else None,
                    "evidence": refs,
                    "claim": "Observed implementation candidate; ownership and product fitness require review.",
                }
            )
        opportunity["reusable_assets"] = reusable_assets
        opportunity["missing_components"] = sorted(
            {
                *opportunity["extraction_plan"]["missing_interfaces"],
                *opportunity["extraction_plan"]["missing_tests"],
                *opportunity["extraction_plan"]["deployment_work"],
            }
        )
        accepted[index] = normalize_opportunity(opportunity, evidence_by_id)
    _assign_rank_labels(accepted)
    extraction = [item["extraction_plan"] for item in accepted]
    market = _market_status(cfg)
    provider = provider_for(cfg.reasoning_provider)
    provider.enrich(
        {
            "intent": intent,
            "capabilities": [
                {k: v for k, v in cap.items() if k != "evidence"}
                for cap in capabilities
            ],
            "opportunities": [item["opportunity_id"] for item in accepted],
        }
    )
    return DiscoveryResult(
        intent, capabilities, accepted, evidence, extraction, market, families, rejected
    )


def _apply_technical_gate(candidates, technical_truth):
    mappings = {
        "Traceable compliance gap assessment": {"rule-evaluation", "report-generation"},
        "Evidence-backed security assessment": {"rule-evaluation", "report-generation"},
        "Bulk intake and qualification service": {
            "document-ingestion",
            "rule-evaluation",
        },
        "Workflow reliability diagnostic": {
            "background-processing",
            "report-generation",
        },
        "Local repository workflow inspector": set(),
        "Reusable paid-workflow launch shell": {
            "authenticated-access",
            "subscription-billing",
        },
    }
    by_key = (
        {c["key"]: c for c in technical_truth.capabilities} if technical_truth else {}
    )
    coverage = technical_truth.summary["coverage"] if technical_truth else {"ratio": 0}
    for item in candidates:
        required = mappings.get(item["title"], set())
        matched = [by_key[key] for key in sorted(required) if key in by_key]
        verified = [c for c in matched if c["status"] == "verified_end_to_end"]
        disconnected = [
            c
            for c in matched
            if c["status"] in {"implemented_but_disconnected", "partially_implemented"}
        ]
        missing = sorted({m for c in matched for m in c["missing_components"]})
        if not technical_truth:
            score, status = 20, "not_performed"
            item["overall_score"] = min(item["overall_score"], 50)
        elif required and len(matched) < len(required):
            score, status = 25, "low"
            item["overall_score"] = min(item["overall_score"], 42)
        elif required and len(verified) == len(required):
            score, status = (
                round(sum(c["confidence"] for c in verified) / len(verified) * 100),
                "high",
            )
        elif any(
            c["status"]
            in {
                "contradicted",
                "configuration_only",
                "test_or_mock_only",
                "schema_only",
                "interface_only",
                "inferred",
                "unknown",
            }
            for c in matched
        ):
            score, status = (
                round(sum(c["confidence"] for c in matched) / len(matched) * 100),
                "low",
            )
            item["overall_score"] = min(item["overall_score"], 42)
        elif verified or disconnected:
            score, status = (
                round(sum(c["confidence"] for c in matched) / len(matched) * 100),
                "moderate",
            )
            item["overall_score"] = min(item["overall_score"], 55)
        else:
            score, status = 30 if matched else 20, "low"
            item["overall_score"] = min(item["overall_score"], 45)
        item.update(
            {
                "technical_verification_status": status,
                "verified_workflows": sorted(
                    {w for c in verified for w in c["supporting_workflow_ids"]}
                ),
                "verified_capabilities": [c["capability_id"] for c in verified],
                "disconnected_capabilities": [c["capability_id"] for c in disconnected],
                "missing_critical_paths": missing
                or (
                    []
                    if status == "high"
                    else [
                        "No verified complete technical path supports every required capability."
                    ]
                ),
                "technical_contradictions": sorted(
                    {e for c in matched for e in c["contradictory_evidence"]}
                ),
                "deep_analysis_coverage": coverage,
                "unsupported_language_coverage": technical_truth.summary[
                    "files_unsupported"
                ]
                if technical_truth
                else None,
                "technical_confidence": score,
                "product_readiness_confidence": min(
                    score, item["completion_score"], 55 if status == "moderate" else 100
                ),
                "speculative": status != "high",
            }
        )
        item["score_components"]["technical_verification"] = score
        if item["speculative"]:
            item["summary"] = (
                "The repository contains components that could support "
                + item["title"].lower()
                + "; a working product was not technically verified."
            )
            item["pursue_reason"] = (
                "Treat as a speculative extraction hypothesis until the missing technical path is proven."
            )


def _evidence_index(audit: AuditResult, maximum: int) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for record in audit.files:
        if not record.text:
            continue
        text = redact_secrets(record.text[:maximum])
        lines = text.splitlines()
        searchable = _semantic_source(record, text)
        detected_terms = sorted(
            {
                term
                for _, _, terms, _ in CAPABILITY_RULES
                for term in terms
                if term in searchable.lower()
            }
        )
        interesting = []
        for number, line in enumerate(lines, 1):
            lower = line.lower()
            if any(term in lower for term in detected_terms):
                interesting.append(number)
        if not interesting and PurePosixPath(record.path).name.lower().startswith(
            "readme"
        ):
            interesting = [1]
        if not interesting:
            continue
        start, end = min(interesting), min(len(lines), max(interesting) + 2)
        evidence.append(
            {
                "evidence_id": _stable_id("ev", record.path, str(start), str(end)),
                "path": record.path,
                "symbol": _symbol(lines, start),
                "lines": f"{start}-{end}",
                "evidence_type": _evidence_type(record),
                "supports": "Contains explicit implementation or product-intent signals used by deterministic discovery.",
                "confidence": 0.9
                if record.role in {"API/routing", "test", "data model"}
                else 0.72,
                "redacted": text != record.text[:maximum],
                "terms": detected_terms,
            }
        )
    return sorted(evidence, key=lambda item: item["evidence_id"])


def _reconstruct_intent(
    audit: AuditResult, evidence: list[dict[str, Any]]
) -> dict[str, Any]:
    readmes = [
        record
        for record in audit.files
        if PurePosixPath(record.path).name.lower().startswith("readme") and record.text
    ]
    manifests = [
        record
        for record in audit.files
        if PurePosixPath(record.path).name == "package.json" and record.text
    ]
    title = audit.target.name
    stated = ""
    source = None
    if readmes:
        match = re.search(r"(?m)^#\s+(.+)$", readmes[0].text or "")
        if match:
            title, source = match.group(1).strip(), readmes[0].path
        stated = (readmes[0].text or "")[:500].strip()
    elif manifests:
        try:
            package = json.loads(manifests[0].text or "{}")
            title = package.get("name") or title
            stated = package.get("description") or ""
            source = manifests[0].path
        except json.JSONDecodeError:
            pass
    implemented_terms = Counter(term for item in evidence for term in item["terms"])
    primary = implemented_terms.most_common(3)
    reality = (
        ", ".join(term for term, _ in primary) or "only structural project signals"
    )
    contradictions = []
    if re.search(r"\b(production[- ]ready|complete|fully implemented)\b", stated, re.I):
        tested = sum(project.test_files for project in audit.projects)
        if tested == 0:
            contradictions.append(
                "Documentation claims maturity, but no tests were detected."
            )
        elif (
            not audit.projects
            or max(project.appraisal_score for project in audit.projects) < 75
        ):
            contradictions.append(
                "Documentation claims maturity, but the deterministic completeness evidence remains below the crown-jewel threshold."
            )
    return {
        "apparent_original_product": title,
        "intended_user": "Not explicit in repository evidence",
        "intended_workflow": stated.splitlines()[0][:240] if stated else "Not explicit",
        "intended_business_model": _business_model(audit),
        "actual_implementation_state": reality,
        "stated_vs_implemented": contradictions
        or ["No material contradiction crossed the deterministic threshold."],
        "confidence": round(min(0.95, 0.35 + 0.08 * len(evidence)), 2),
        "evidence_references": [
            item["evidence_id"] for item in evidence if item["path"] == source
        ][:3],
    }


def _capabilities(
    audit: AuditResult, evidence: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_path = {record.path: record for record in audit.files}
    capabilities = []
    for key, name, terms, description in CAPABILITY_RULES:
        matched = [item for item in evidence if set(terms) & set(item["terms"])]
        paths = sorted({item["path"] for item in matched})
        if not paths:
            continue
        tests = sum(1 for path in paths if (by_path[path].role == "test"))
        implemented = sum(
            1
            for path in paths
            if by_path[path].role
            in {"source", "API/routing", "data model", "UI/component"}
        )
        completion = min(
            100, 25 + implemented * 12 + tests * 10 + min(20, len(paths) * 3)
        )
        capabilities.append(
            {
                "schema_version": "1.0",
                "capability_id": _stable_id("cap", key),
                "key": key,
                "name": name,
                "description": description,
                "supporting_files": paths,
                "symbols": [item["symbol"] for item in matched if item["symbol"]][:8],
                "completion_level": completion,
                "test_coverage": "present" if tests else "not evidenced",
                "deployment_readiness": "partial"
                if any("Docker" in p.kinds for p in audit.projects)
                else "not evidenced",
                "dependencies": sorted(
                    {kind for p in audit.projects for kind in p.kinds}
                ),
                "security_concerns": [
                    "Requires review of authentication, authorization, input handling, and secret management."
                ],
                "reusability": "high" if len(paths) >= 3 else "medium",
                "coupling": "medium",
                "extraction_difficulty": "low" if len(paths) <= 3 else "moderate",
                "evidence_confidence": min(100, 35 + 12 * len(matched)),
                "evidence": [item["evidence_id"] for item in matched][:12],
            }
        )
    return capabilities


def _opportunity_candidates(audit, intent, capabilities, families, cfg):
    by_key = {cap["key"]: cap for cap in capabilities}
    templates = [
        (
            {"compliance", "reporting"},
            "Traceable compliance gap assessment",
            "Compliance teams",
            "Head of Compliance",
            "A policy or control set must be reviewed before an audit",
            "compliance-gap-report",
            "paid diagnostic",
        ),
        (
            {"security", "reporting"},
            "Evidence-backed security assessment",
            "Infrastructure security teams",
            "CISO or security director",
            "A release, incident, or supplier review requires defensible findings",
            "security-assessment",
            "productized service",
        ),
        (
            {"bulk-ingestion", "evaluation"},
            "Bulk intake and qualification service",
            "Operations teams processing high-volume records",
            "VP Operations",
            "A backlog of records must be triaged quickly",
            "intake-qualification",
            "productized service",
        ),
        (
            {"workflow", "reporting"},
            "Workflow reliability diagnostic",
            "Teams operating multi-step automations",
            "Automation or platform lead",
            "Jobs are failing without a traceable explanation",
            "workflow-diagnostic",
            "paid diagnostic",
        ),
        (
            {"developer-cli"},
            "Local repository workflow inspector",
            "Software maintainers with inherited or abandoned code",
            "Engineering manager",
            "A code estate must be understood before funding or migration",
            "repository-inspector",
            "desktop application",
        ),
        (
            {"authentication", "billing"},
            "Reusable paid-workflow launch shell",
            "Small product teams validating a paid workflow",
            "Founder or product lead",
            "A validated workflow needs controlled access and payment",
            "paid-workflow-shell",
            "licensing arrangement",
        ),
    ]
    candidates = []
    for required, title, user, buyer, trigger, slug, offer in templates:
        present = required & set(by_key)
        if present != required and not (required == {"developer-cli"} and present):
            continue
        supporting = [by_key[key] for key in sorted(required)]
        ev_ids = sorted({ev for cap in supporting for ev in cap["evidence"]})
        evidence_score = min(
            100,
            round(
                sum(cap["evidence_confidence"] for cap in supporting) / len(supporting)
            ),
        )
        completion = round(
            sum(cap["completion_level"] for cap in supporting) / len(supporting)
        )
        effort = (
            "low" if completion >= 70 else "moderate" if completion >= 45 else "high"
        )
        commercial = max(
            20, min(80, 48 + 4 * len(ev_ids) - (10 if effort == "high" else 0))
        )
        overall = round(
            evidence_score * 0.35
            + completion * 0.25
            + commercial * 0.2
            + (75 if effort == "low" else 55 if effort == "moderate" else 30) * 0.2
        )
        op_id = _stable_id("opp", slug, *[cap["capability_id"] for cap in supporting])
        product_output = f"A bounded {title.lower()} with a traceable evidence report"
        wedge = {
            "initial_segment": user,
            "initial_use_case": trigger,
            "required_input": "Customer-provided files or structured records",
            "delivered_output": product_output,
            "time_to_first_value": "After one bounded intake and review cycle",
            "required_features": [cap["name"] for cap in supporting],
            "excluded_features": [
                "General marketplace",
                "Broad autonomous platform",
                "Unrelated modules",
            ],
            "manual_work_allowed": "Expert review and customer onboarding may remain manual during validation.",
            "why_narrower": "It sells the best-evidenced workflow without completing the original broad product.",
        }
        extraction_plan = {
            "opportunity_id": op_id,
            "reuse": sorted(
                {path for cap in supporting for path in cap["supporting_files"]}
            ),
            "isolate": [cap["name"] for cap in supporting],
            "rewrite": [
                "Any interface that directly couples the workflow to unrelated product modules"
            ],
            "discard": ["Unrelated unfinished surfaces"],
            "dependencies_to_remove": [
                "Dependencies not reached by the proposed workflow"
            ],
            "data_migrations": [
                "Confirm schema ownership and customer-data boundaries"
            ],
            "security_work": [
                "Threat model inputs",
                "Verify authorization",
                "Remove embedded secrets",
                "Validate output redaction",
            ],
            "missing_interfaces": [
                "A bounded intake contract",
                "A customer-facing result delivery path",
            ],
            "missing_tests": [
                "End-to-end test for the proposed wedge",
                "Adversarial input tests",
            ],
            "deployment_work": [
                "Create an isolated deployment or signed local package"
            ],
            "usable_existing_implementation_percent": completion,
            "relative_effort": effort,
            "technical_risks": [
                "Disconnected modules may not integrate",
                "Repository evidence does not prove production reliability",
            ],
        }
        positioning = f"For {user.lower()} experiencing {trigger.lower()}, {title} provides {product_output.lower()}. Unlike manual code archaeology or generic consulting, it uses the repository-supported {', '.join(cap['name'].lower() for cap in supporting)} capabilities."
        candidates.append(
            {
                "schema_version": "1.0",
                "opportunity_id": op_id,
                "title": title,
                "summary": product_output,
                "category": offer,
                "source_projects": [p.root for p in audit.projects],
                "target_user": user,
                "economic_buyer": buyer,
                "trigger_event": trigger,
                "job_to_be_done": product_output,
                "existing_alternative": "Manual review, spreadsheets, and general-purpose consulting",
                "customer_outcome": "A bounded, reviewable result tied to supplied evidence",
                "supporting_capability_ids": [
                    cap["capability_id"] for cap in supporting
                ],
                "evidence": ev_ids,
                "contradictions": intent["stated_vs_implemented"],
                "completion_score": completion,
                "evidence_score": evidence_score,
                "extraction_effort": effort,
                "commercial_confidence": commercial,
                "market_validation_status": "not_performed",
                "differentiation": "Existing implemented workflow components reduce speculative build work.",
                "wedge": wedge,
                "pricing_hypothesis": {
                    "status": "hypothesis",
                    "model": "fixed-fee pilot",
                    "low": 500,
                    "base": 1500,
                    "high": 5000,
                    "unit": "one bounded assessment",
                    "assumptions": [
                        "Buyer urgency and willingness to pay are unvalidated"
                    ],
                    "expected_objection": "The customer may prefer an internal manual review.",
                },
                "gtm": _gtm(title, user, buyer, trigger, positioning, product_output),
                "extraction_plan": extraction_plan,
                "risks": [
                    "Demand has not been externally validated",
                    "Evidence may describe disconnected prototypes",
                ],
                "unknowns": [
                    "Who has paid for this outcome?",
                    "Can the workflow handle representative customer data safely?",
                ],
                "next_validation_steps": [
                    "Interview 15 target users",
                    "Run 3 concierge demonstrations",
                    "Ask for a paid pilot before broadening scope",
                ],
                "pursue_reason": f"{len(ev_ids)} traceable evidence items support the required capabilities.",
                "reject_reason": "Reject if prospects do not rank the triggering event as urgent or no paid pilot emerges.",
                "overall_score": overall,
                "confidence_score": min(95, evidence_score),
                "commercial_risk": 100 - commercial,
                "score_components": {
                    "repository_evidence": evidence_score,
                    "capability_completeness": completion,
                    "buyer_urgency": 55,
                    "ease_of_reach": 50,
                    "time_to_value": 60,
                    "revenue_potential": commercial,
                    "competitive_intensity": 40,
                    "dependency_risk": 45,
                    "security_burden": 45,
                    "market_validation_confidence": 0,
                },
                "evidence_that_changes_ranking": [
                    "Paid pilot acceptance",
                    "Representative workflow failure",
                    "Verified competitor pricing",
                ],
                "generic_language_penalty": _generic_penalty(title + " " + positioning),
                "rank_labels": [],
            }
        )
    return candidates


def _gtm(title, user, buyer, trigger, positioning, output):
    return {
        "positioning": positioning,
        "offer_model": "productized service or paid diagnostic",
        "deliverable": output,
        "scope": "One bounded customer workflow",
        "customer_commitment": "Provide representative inputs and a review interview",
        "seller_commitment": "Deliver an evidence-linked result and limitations",
        "expansion_path": "Automate only repeated paid steps",
        "channels": {
            "primary": f"Targeted outbound to {buyer}s at organizations showing the trigger event",
            "secondary": "Design-partner referrals",
            "trigger_events": [trigger],
        },
        "sales_assets": {
            "headline": f"Turn {trigger.lower()} into a traceable result.",
            "subheadline": f"{title} gives {user.lower()} a bounded output backed by explicit evidence.",
            "benefits": [
                "See which evidence supports every finding",
                "Start with a bounded workflow",
                "Validate value before expanding software",
            ],
            "email": f"Subject: {trigger}\nWe built a focused way to deliver {output.lower()}. I’m looking for one design partner with this exact workflow. Worth a 20-minute evidence review?",
            "direct_message": f"Are you currently handling this manually: {trigger.lower()}? We are testing a bounded, evidence-backed alternative.",
            "discovery_opening": "I want to understand the last time this workflow became urgent and what the delay cost.",
            "discovery_questions": [
                "What triggered the last instance?",
                "Who owned the result?",
                "What was done manually?",
                "What made the result trustworthy?",
                "Would a bounded paid pilot replace any current spend?",
            ],
            "pilot_offer": f"One fixed-scope {title.lower()} using representative inputs, with an evidence appendix and limitations.",
            "call_to_action": "Book a 20-minute workflow review.",
        },
        "validation_30_day": {
            "assumptions": [
                "The trigger is urgent",
                "The output is budget-worthy",
                "Repository capabilities shorten delivery",
            ],
            "experiments": [
                "15 interviews",
                "3 concierge demos",
                "At least 1 explicitly paid pilot request",
            ],
            "prospects": 30,
            "interview_goal": "Reconstruct actual recent workflows and buying authority",
            "demo": "A redacted example result, not a broad platform",
            "paid_pilot_threshold": "At least one paid pilot from 30 qualified contacts",
            "success": "Two paid pilots or one paid pilot plus three concrete follow-ups",
            "warning": "Interest without access to a buyer or real inputs",
            "kill": "Zero prospects describe the trigger as urgent and zero paid commitment after 30 qualified contacts",
            "pivot": "Repeated demand for a different output supported by the same capabilities",
            "continue_evidence": "Paid use, repeat use, or referral to another buyer",
        },
    }


def _quality_gate(candidates, minimum):
    accepted, rejected = [], []
    for item in candidates:
        reasons = []
        if len(item["evidence"]) < 2:
            reasons.append("fewer than two evidence items")
        if item["evidence_score"] < minimum:
            reasons.append("evidence score below threshold")
        if not item["target_user"] or not item["trigger_event"]:
            reasons.append("customer or trigger missing")
        if not item["extraction_plan"]["reuse"]:
            reasons.append("no credible extraction path")
        if not item["unknowns"] or not item["reject_reason"]:
            reasons.append("missing uncertainty or failure reason")
        if item["generic_language_penalty"] >= 20:
            reasons.append("generic marketing language")
        if reasons:
            rejected.append(
                {
                    "opportunity_id": item["opportunity_id"],
                    "title": item["title"],
                    "reasons": reasons,
                }
            )
        else:
            accepted.append(item)
    return accepted, rejected


def _assign_rank_labels(items):
    dimensions = {
        "Highest probability of near-term revenue": lambda x: x["commercial_confidence"]
        - (20 if x["extraction_effort"] == "high" else 0),
        "Strongest technical differentiation": lambda x: x["evidence_score"],
        "Lowest-cost extraction": lambda x: {"low": 3, "moderate": 2, "high": 1}.get(
            x["extraction_effort"], 0
        ),
        "Largest strategic opportunity": lambda x: x["overall_score"]
        + x["commercial_confidence"],
        "Best productized-service opportunity": lambda x: 100
        if "service" in x["category"] or "diagnostic" in x["category"]
        else 0,
        "Most surprising hidden product": lambda x: len(x["supporting_capability_ids"]),
    }
    for label, key in dimensions.items():
        if items:
            max(items, key=lambda x: (key(x), x["opportunity_id"]))[
                "rank_labels"
            ].append(label)


def _project_families(audit):
    groups = defaultdict(list)
    for project in audit.projects:
        name = re.sub(
            r"(?i)([-_ ]?(backup|copy|old|archive|worktree|pass)\d*)+$",
            "",
            project.root,
        )
        groups[name or project.root].append(project.root)
    return [
        {
            "family_id": _stable_id("family", name),
            "canonical_hint": name,
            "members": sorted(members),
            "treat_as_separate_products": len(members) == 1,
        }
        for name, members in sorted(groups.items())
    ]


def _market_status(cfg):
    if not cfg.market_validation:
        return {
            "schema_version": "1.0",
            "status": "not_performed",
            "reason": "External market validation was not enabled.",
            "repository_findings_are_market_validated": False,
            "repository_facts": [],
            "external_facts": [],
            "inferences": [],
            "assumptions": ["Buyer urgency and pricing remain hypotheses."],
            "unknowns": [
                "Competitors, public pricing, purchase behavior, and current regulations were not checked."
            ],
        }
    if cfg.offline:
        return {
            "schema_version": "1.0",
            "status": "blocked",
            "reason": "Offline mode prohibits external market validation.",
            "repository_findings_are_market_validated": False,
        }
    return {
        "schema_version": "1.0",
        "status": "not_configured",
        "reason": "Market validation was enabled but no external research adapter is configured; no repository content was transmitted.",
        "repository_findings_are_market_validated": False,
    }


def _business_model(audit):
    text = "\n".join(record.text or "" for record in audit.files)
    if re.search(r"stripe|subscription|checkout|billing", text, re.I):
        return "Paid software or subscription signals detected"
    return "Not inferable"


def _evidence_type(record):
    return {
        "test": "test",
        "documentation": "stated_intent",
        "API/routing": "implemented_workflow",
        "data model": "schema",
        "UI/component": "user_interface",
    }.get(record.role or "", "implementation_signal")


def _symbol(lines, number):
    for line in lines[max(0, number - 2) : number + 2]:
        match = re.search(
            r"(?:def|class|function|const|async\s+function)\s+([A-Za-z_][A-Za-z0-9_]*)",
            line,
        )
        if match:
            return match.group(1)
    return None


def _semantic_source(record: FileRecord, text: str) -> str:
    if record.role not in {
        "source",
        "API/routing",
        "data model",
        "UI/component",
        "test",
    }:
        return ""
    without_blocks = re.sub(r"(?s)(['\"]{3}).*?\1", " ", text)
    without_strings = re.sub(r"""(['"])(?:\\.|(?!\1).)*\1""", " ", without_blocks)
    without_comments = re.sub(r"(?m)(#|//).*$", " ", without_strings)
    return without_comments


def _stable_id(prefix, *parts):
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _generic_penalty(text):
    lower = text.lower()
    return 20 * sum(phrase in lower for phrase in GENERIC_PHRASES)
