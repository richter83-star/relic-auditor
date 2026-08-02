from __future__ import annotations

from dataclasses import asdict
from pathlib import PurePosixPath
from typing import Iterable

from ..models import AuditResult, FileRecord
from ..safety import redact_secrets
from .definitions import CAPABILITY_ORDER, CAPABILITY_RULES, CapabilityRule
from .schemas import (
    AcquisitionConfig,
    AcquisitionResult,
    CapabilityEvidence,
    CapabilityMatch,
    ItemAssessment,
)


_BUILD_ORDER = (
    ("governance_boundary", "Define and test the authority boundary first."),
    ("audit_log", "Make every proposal and decision attributable before adding autonomy."),
    ("approval_queue", "Require an explicit approval transition for consequential actions."),
    ("goal_registry", "Store bounded goals with owners, limits, status, and stop conditions."),
    ("orchestrator", "Connect only approved components through a deterministic coordinator."),
    ("autonomy_loop", "Add a step-limited loop with failure, timeout, and termination states."),
    (
        "self_improvement_proposal",
        "Generate reviewable proposals; keep evaluation and application outside the loop.",
    ),
    (
        "resource_request",
        "Permit bounded resource requests only; provisioning remains externally controlled.",
    ),
)


def analyze_capability_acquisition(
    audit: AuditResult,
    config: AcquisitionConfig | None = None,
) -> AcquisitionResult:
    active = config or AcquisitionConfig()
    active.validate()
    items = [_assess_item(record, active) for record in audit.files]
    summary = [_summarize_capability(key, items) for key in CAPABILITY_ORDER]
    candidates = _rank_candidates(items, active.max_candidates)
    missing = [
        {
            "capability": row["capability"],
            "title": row["title"],
            "status": "missing" if row["confidence"] < 0.18 else "weak",
            "confidence": row["confidence"],
            "reason": (
                "No sufficiently specific static evidence was found."
                if row["confidence"] < 0.18
                else "Only weak, documentary, test-only, or isolated evidence was found."
            ),
        }
        for row in summary
        if row["confidence"] < 0.45
    ]
    build_path = []
    by_key = {row["capability"]: row for row in summary}
    for sequence, (key, rationale) in enumerate(_BUILD_ORDER, start=1):
        row = by_key[key]
        build_path.append(
            {
                "sequence": sequence,
                "capability": key,
                "title": row["title"],
                "disposition": (
                    "reuse candidate"
                    if row["confidence"] >= 0.62
                    else "validate and adapt"
                    if row["confidence"] >= 0.32
                    else "build missing piece"
                ),
                "confidence": row["confidence"],
                "rationale": rationale,
                "acceptance_gate": _acceptance_gate(key),
            }
        )
    risks = _risk_notes(audit, summary, candidates)
    return AcquisitionResult(
        target=audit.target,
        items=items,
        capability_summary=summary,
        best_candidates=candidates,
        missing_pieces=missing,
        suggested_build_path=build_path,
        risk_notes=risks,
        scan_summary={
            "files_observed": len(audit.files),
            "items_with_text_inspected": sum(item.inspected for item in items),
            "items_with_capability_matches": sum(bool(item.capability_matches) for item in items),
            "zip_members_observed": sum(item.source == "zip" for item in items),
            "archives": len(audit.archives),
            "unsafe_archive_members": sum(
                len(archive.get("unsafe_members", [])) for archive in audit.archives
            ),
            "deterministic": True,
            "llm_used": False,
            "source_executed": False,
            "source_modified": False,
        },
    )


def _assess_item(record: FileRecord, config: AcquisitionConfig) -> ItemAssessment:
    context, factor = _context(record.path, record.role)
    matches = []
    text = record.text or ""
    for rule in CAPABILITY_RULES:
        match = _match_rule(record, text, rule, factor, context, config)
        if match is not None and match.confidence >= config.minimum_signal_score:
            matches.append(match)
    matches.sort(key=lambda item: (-item.confidence, item.capability))
    notes = list(record.warnings)
    if record.text is None:
        notes.append("content not inspected (binary, unsupported, skipped, unreadable, or over limit)")
    return ItemAssessment(
        path=redact_secrets(record.path),
        source=record.source,
        role=record.role,
        size=record.size,
        inspected=record.text is not None,
        confidence=round(max((match.confidence for match in matches), default=0.0), 4),
        capability_matches=matches,
        notes=sorted(set(redact_secrets(note) for note in notes)),
    )


def _match_rule(
    record: FileRecord,
    text: str,
    rule: CapabilityRule,
    factor: float,
    context: str,
    config: AcquisitionConfig,
) -> CapabilityMatch | None:
    evidence: list[CapabilityEvidence] = []
    seen_signals: set[str] = set()
    lines = text.splitlines()
    searchable = f"{record.path}\n{text}"
    for signal in rule.signals:
        match = signal.pattern.search(searchable)
        if match is None or signal.name in seen_signals:
            continue
        seen_signals.add(signal.name)
        line_number, excerpt = _locate(lines, signal.pattern, record.path)
        evidence.append(
            CapabilityEvidence(
                path=redact_secrets(record.path),
                line=line_number,
                signal=signal.name,
                matched=redact_secrets(match.group(0)[:160]),
                excerpt=redact_secrets(excerpt),
                weight=signal.weight,
                source=record.source,
            )
        )
        if len(evidence) >= config.max_evidence_per_match:
            break
    if not evidence:
        return None
    raw = sum(item.weight for item in evidence)
    diversity_bonus = min(0.16, max(0, len(evidence) - 1) * 0.04)
    confidence = round(min(1.0, (raw + diversity_bonus) * factor), 4)
    return CapabilityMatch(
        capability=rule.key,
        title=rule.title,
        confidence=confidence,
        confidence_label=_label(confidence),
        evidence=evidence,
        context=context,
        reusable=confidence >= 0.52 and context == "source",
    )


def _locate(
    lines: list[str],
    pattern: object,
    fallback: str,
) -> tuple[int, str]:
    for index, line in enumerate(lines, start=1):
        if pattern.search(line):  # type: ignore[attr-defined]
            return index, line.strip()[:320]
    return 0, fallback[:320]


def _context(path: str, role: str | None) -> tuple[str, float]:
    lowered = path.lower()
    parts = PurePosixPath(lowered.replace("!", "/")).parts
    if role == "test" or any(part in {"test", "tests", "__tests__"} for part in parts):
        return "test", 0.72
    if role == "documentation" or lowered.endswith((".md", ".rst", ".txt")):
        return "documentation", 0.55
    if role in {"configuration", "manifest"}:
        return "configuration", 0.66
    if any(token in lowered for token in ("example", "sample", "fixture", "mock")):
        return "example", 0.60
    return "source", 1.0


def _summarize_capability(key: str, items: Iterable[ItemAssessment]) -> dict[str, object]:
    rule = next(item for item in CAPABILITY_RULES if item.key == key)
    matches = [
        (item, match)
        for item in items
        for match in item.capability_matches
        if match.capability == key
    ]
    matches.sort(key=lambda pair: (-pair[1].confidence, pair[0].path))
    top = matches[:3]
    combined = 0.0
    for index, (_item, match) in enumerate(top):
        combined += match.confidence * (1.0 if index == 0 else 0.18)
    confidence = round(min(1.0, combined), 4)
    return {
        "capability": key,
        "title": rule.title,
        "description": rule.description,
        "confidence": confidence,
        "confidence_label": _label(confidence),
        "status": (
            "strong candidate"
            if confidence >= 0.72
            else "candidate"
            if confidence >= 0.45
            else "weak evidence"
            if confidence >= 0.18
            else "not detected"
        ),
        "candidate_count": len(matches),
        "best_paths": [item.path for item, _match in top],
        "evidence_count": sum(len(match.evidence) for _item, match in matches),
    }


def _rank_candidates(items: list[ItemAssessment], limit: int) -> list[dict[str, object]]:
    candidates = []
    for item in items:
        for match in item.capability_matches:
            if match.confidence < 0.32:
                continue
            candidates.append(
                {
                    "rank": 0,
                    "path": item.path,
                    "source": item.source,
                    "context": match.context,
                    "capability": match.capability,
                    "title": match.title,
                    "confidence": match.confidence,
                    "confidence_label": match.confidence_label,
                    "reusable": match.reusable,
                    "evidence": [asdict(evidence) for evidence in match.evidence],
                    "reuse_note": (
                        "Source-level candidate; isolate behind an adapter and verify tests and boundaries."
                        if match.reusable
                        else "Evidence requires validation; do not treat documentation or tests as implemented capability."
                    ),
                }
            )
    candidates.sort(
        key=lambda item: (
            -float(item["confidence"]),
            str(item["capability"]),
            str(item["path"]),
        )
    )
    for rank, candidate in enumerate(candidates[:limit], start=1):
        candidate["rank"] = rank
    return candidates[:limit]


def _risk_notes(
    audit: AuditResult,
    summary: list[dict[str, object]],
    candidates: list[dict[str, object]],
) -> list[str]:
    by_key = {str(item["capability"]): float(item["confidence"]) for item in summary}
    notes = [
        "Static matches can be incomplete or misleading; every candidate requires human code review and isolated tests.",
        "Capability evidence is not permission to connect, execute, install, deploy, or grant authority to any component.",
        "Resource Request findings are request/approval primitives only; Relic does not enable self-provisioning.",
    ]
    if by_key["autonomy_loop"] >= 0.45 and by_key["governance_boundary"] < 0.45:
        notes.append("An autonomy loop appears stronger than its governance boundary; treat integration as blocked.")
    if by_key["self_improvement_proposal"] >= 0.45 and by_key["approval_queue"] < 0.45:
        notes.append("Improvement proposal logic lacks a comparably strong approval queue; do not automate application.")
    if any(candidate["source"] == "zip" for candidate in candidates):
        notes.append("Some leading candidates are virtual ZIP members; validate archive provenance before reuse.")
    if any(archive.get("status") == "rejected" for archive in audit.archives):
        notes.append("At least one archive exceeded safety limits and was rejected; its contents are intentionally absent.")
    return notes


def _acceptance_gate(key: str) -> str:
    gates = {
        "governance_boundary": "Denied actions remain denied in unit and adversarial boundary tests.",
        "audit_log": "Every state transition records actor, reason, time, inputs, and outcome without secrets.",
        "approval_queue": "No consequential transition occurs without a valid, attributable approval.",
        "goal_registry": "Every goal has owner, bounds, success criteria, expiration, and cancel state.",
        "orchestrator": "Only registered bounded actions can be dispatched; failures are isolated.",
        "autonomy_loop": "Iteration, time, cost, and authority limits terminate deterministically.",
        "self_improvement_proposal": "The component can propose and evaluate but cannot apply its own changes.",
        "resource_request": "Requests are capped and externally approved; the requester cannot provision resources.",
    }
    return gates[key]


def _label(score: float) -> str:
    if score >= 0.72:
        return "high"
    if score >= 0.45:
        return "medium"
    if score >= 0.18:
        return "low"
    return "none"

