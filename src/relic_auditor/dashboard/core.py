from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping

from ..audit import audit_estate
from ..capability_acquisition import (
    AcquisitionResult,
    analyze_capability_acquisition,
    write_acquisition_reports,
)
from ..models import AuditResult, Candidate, ScanLimits
from ..llm import (
    LLMReasoningConfig,
    LLMReasoningResult,
    reason_about_acquisition,
    write_llm_reports,
)
from ..llm import claude_code
from ..llm.config import ProfileStore
from ..llm.schemas import LLMProfile
from ..product_discovery import DiscoveryConfig, DiscoveryResult, discover_products
from ..product_discovery.entitlements import Entitlement, FREE_ENTITLEMENT
from ..product_discovery.reports import write_product_reports
from ..reports import write_reports
from ..safety import redact_structure
from ..technical_truth import (
    TechnicalTruthConfig,
    TechnicalTruthResult,
    analyze_technical_truth,
)
from ..technical_truth.reports import write_technical_truth_reports


ProgressCallback = Callable[[int, str], None]
VALID_DECISIONS = frozenset({"keep", "extract", "archive", "review"})

#: Reasoning provider kinds surfaced by the dashboard. Claude Max runs through
#: the local Claude Code CLI on subscription billing and is not a direct
#: Anthropic API connection; the other kinds use configured profiles.
PROVIDER_KIND_LABELS = {
    "claude-max": "Claude Code / Claude Max (subscription via local Claude Code CLI)",
    "api-key": "Anthropic or OpenAI-compatible API key (metered API billing)",
    "oauth": "Generic OAuth provider (standards-based profile)",
}
DEFAULT_CLAUDE_MAX_PROFILE = "Claude-Max"


def ensure_claude_max_profile(
    name: str = DEFAULT_CLAUDE_MAX_PROFILE,
    *,
    model: str = "sonnet",
    effort: str = claude_code.DEFAULT_EFFORT,
    store: ProfileStore | None = None,
) -> LLMProfile:
    """Create or update the dashboard's Claude Code subscription profile."""

    if model not in claude_code.MODEL_ALIASES:
        raise ValueError(
            "Claude Code model alias must be one of: "
            + ", ".join(claude_code.MODEL_ALIASES)
        )
    profile = LLMProfile(
        name=name,
        protocol="claude-code",
        model=model,
        base_url="",
        auth_mode="claude-subscription",
        effort=effort,
    )
    profile.validate()
    (store or ProfileStore()).save(profile)
    return profile


def claude_max_status(
    name: str = DEFAULT_CLAUDE_MAX_PROFILE,
    *,
    store: ProfileStore | None = None,
    runner: claude_code.SubprocessRunner | None = None,
) -> dict[str, object]:
    """Safe readiness report for the dashboard; never includes account

    emails, organization identifiers, tokens, or credential paths."""

    try:
        profile = (store or ProfileStore()).get(name)
    except KeyError:
        profile = LLMProfile(
            name=name,
            protocol="claude-code",
            model="sonnet",
            base_url="",
            auth_mode="claude-subscription",
            effort=claude_code.DEFAULT_EFFORT,
        )
    return claude_code.safe_status(profile, runner=runner)


def launch_claude_login() -> int:
    """Open the official ``claude auth login`` flow. Relic never intercepts

    or parses the resulting OAuth token."""

    return claude_code.login()


@dataclass(frozen=True)
class DashboardOptions:
    """Bounded local scan controls exposed by the desktop interface."""

    include_hidden: bool = False
    max_file_mb: int = 10
    max_zip_members: int = 20_000
    technical_truth: bool = True
    product_discovery: bool = False
    capability_acquisition: bool = False
    max_opportunities: int = 6
    technical_max_file_mb: int = 2
    max_graph_nodes: int = 100_000
    workflow_depth: int = 12
    max_data_flow_edges: int = 50_000
    llm_profile: str | None = None

    def validate(self) -> None:
        values = {
            "max_file_mb": self.max_file_mb,
            "max_zip_members": self.max_zip_members,
            "max_opportunities": self.max_opportunities,
            "technical_max_file_mb": self.technical_max_file_mb,
            "max_graph_nodes": self.max_graph_nodes,
            "workflow_depth": self.workflow_depth,
            "max_data_flow_edges": self.max_data_flow_edges,
        }
        invalid = [name for name, value in values.items() if value <= 0]
        if invalid:
            raise ValueError(f"scan limits must be positive: {', '.join(invalid)}")
        if self.llm_profile is not None and not self.llm_profile.strip():
            raise ValueError("LLM profile cannot be blank")


@dataclass
class DashboardBundle:
    """All in-memory results produced by one dashboard scan."""

    audit: AuditResult
    options: DashboardOptions
    technical_truth: TechnicalTruthResult | None = None
    discovery: DiscoveryResult | None = None
    acquisition: AcquisitionResult | None = None
    llm_reasoning: LLMReasoningResult | None = None
    entitlement: Entitlement = FREE_ENTITLEMENT


@dataclass(frozen=True)
class ReportHistoryEntry:
    """One automatically exported audit in the product's report history."""

    project: str
    scan: str
    directory: Path
    full_report: Path | None


_WINDOWS_INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def default_reports_root(documents: Path | None = None) -> Path:
    """Return Relic's stable, per-user report root.

    The GUI supplies the operating system's real Documents location.  The
    optional argument keeps the path rule independently testable and avoids a
    Qt dependency in the audit engine.
    """

    base = documents if documents is not None else Path.home() / "Documents"
    return base.expanduser() / "Relic Auditor" / "Reports"


def automatic_report_directory(
    target: Path,
    reports_root: Path,
    *,
    generated_at: datetime | None = None,
) -> Path:
    """Choose ``Reports/<project> reports/<scan timestamp>`` without collision."""

    name = _WINDOWS_INVALID_NAME.sub("-", target.name).strip(" .") or "Unnamed"
    group = reports_root.expanduser() / f"{name} reports"
    stamp = (generated_at or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    candidate = group / stamp
    suffix = 2
    while candidate.exists():
        candidate = group / f"{stamp}-{suffix}"
        suffix += 1
    return candidate


def list_report_history(reports_root: Path) -> list[ReportHistoryEntry]:
    """List prior automatic exports newest first, tolerating partial folders."""

    root = reports_root.expanduser()
    if not root.is_dir():
        return []
    entries: list[ReportHistoryEntry] = []
    for group in root.iterdir():
        if not group.is_dir():
            continue
        project = group.name[:-8] if group.name.lower().endswith(" reports") else group.name
        for scan in group.iterdir():
            if not scan.is_dir():
                continue
            preferred = scan / "estate-report.md"
            if not preferred.is_file():
                markdown = sorted(scan.glob("*.md"))
                preferred = markdown[0] if markdown else None
            entries.append(
                ReportHistoryEntry(
                    project=project,
                    scan=scan.name,
                    directory=scan,
                    full_report=preferred,
                )
            )
    return sorted(entries, key=lambda item: (item.scan, item.project), reverse=True)


def summarize_dashboard_bundle(bundle: DashboardBundle) -> dict[str, str]:
    """Translate deterministic findings into the four product-level answers."""

    audit = bundle.audit
    kinds = sorted({kind for project in audit.projects for kind in project.kinds})
    kind_text = ", ".join(kinds[:5]) if kinds else "unclassified source"
    found = (
        f"Relic inspected {len(audit.files):,} files across "
        f"{len(audit.projects):,} project roots. It recognized {kind_text}. "
        f"It also found {len(audit.archives):,} archives and "
        f"{len(audit.duplicate_groups):,} byte-identical duplicate groups."
    )

    strong_projects = [
        project
        for project in audit.projects
        if project.appraisal_category in {"Crown jewel", "Valuable system"}
    ]
    opportunities = bundle.discovery.opportunities if bundle.discovery else []
    reusable = bundle.acquisition.best_candidates if bundle.acquisition else []
    value_parts = [
        f"{len(strong_projects):,} project roots scored as valuable systems or crown jewels",
        f"{len(audit.extract_candidates):,} assets recommended for extraction",
        f"{len(reusable):,} reusable-asset matches",
    ]
    if opportunities:
        names = [str(item.get("title") or "Untitled opportunity") for item in opportunities[:3]]
        value_parts.append("leading opportunities: " + "; ".join(names))
    valuable = "Relic identified " + ", ".join(value_parts) + "."

    truth = bundle.technical_truth
    contradictions = len(truth.contradictions) if truth else 0
    incomplete_workflows = (
        sum(
            item.get("completion_status") != "verified_end_to_end"
            for item in truth.workflows
        )
        if truth
        else 0
    )
    disconnected = (
        sum(
            item.get("status") not in {"verified_end_to_end"}
            for item in truth.capabilities
        )
        if truth
        else 0
    )
    risk_parts = [
        f"{contradictions:,} contradictions",
        f"{incomplete_workflows:,} incomplete or interface-only workflows",
        f"{disconnected:,} capabilities not verified end to end",
        f"{len(audit.warnings):,} scan warnings",
    ]
    risky = (
        "The evidence shows " + ", ".join(risk_parts) + ". "
        "These are review signals, not proof that files should be deleted."
    )

    if opportunities:
        lead = str(opportunities[0].get("title") or "the highest-ranked opportunity")
        next_step = (
            f"Start by reviewing {lead}, then confirm its missing pieces and "
            "extraction plan. Use View full report for the evidence and review "
            "every Recommended Action before changing the source estate."
        )
    elif audit.extract_candidates:
        next_step = (
            "Review the extraction candidates first, confirm their dependencies, "
            "then use View full report before making any source change."
        )
    else:
        next_step = (
            "Open the full report, review and resolve the highest-confidence "
            "risks, and run another audit after the estate has been organized."
        )

    return {
        "found": found,
        "valuable": valuable,
        "risky": risky,
        "next": next_step,
    }


def run_dashboard_audit(
    target: Path,
    options: DashboardOptions | None = None,
    progress: ProgressCallback | None = None,
    *,
    entitlement: Entitlement = FREE_ENTITLEMENT,
) -> DashboardBundle:
    """Run the existing engines without writing reports or a persistent cache."""

    active = options or DashboardOptions()
    active.validate()
    resolved_target = target.expanduser().resolve()
    _progress(progress, 5, "Validating the selected estate")
    if not resolved_target.exists():
        raise FileNotFoundError(f"target does not exist: {resolved_target}")
    if not resolved_target.is_dir():
        raise NotADirectoryError(f"target is not a folder: {resolved_target}")

    _progress(progress, 15, "Inventorying files and inspecting ZIPs virtually")
    audit = audit_estate(
        resolved_target,
        limits=ScanLimits(
            max_file_bytes=active.max_file_mb * 1024 * 1024,
            max_zip_members=active.max_zip_members,
        ),
        include_hidden=active.include_hidden,
    )

    truth = None
    run_truth = active.technical_truth or active.product_discovery
    if run_truth:
        _progress(progress, 48, "Reconstructing technical truth and reachability")
        truth = analyze_technical_truth(
            audit,
            TechnicalTruthConfig(
                max_file_size=active.technical_max_file_mb * 1024 * 1024,
                max_graph_nodes=active.max_graph_nodes,
                workflow_depth=active.workflow_depth,
                use_persistent_cache=False,
                resolve_git_lineage=True,
                max_data_flow_edges=active.max_data_flow_edges,
            ),
        )

    acquisition = None
    if active.capability_acquisition or active.llm_profile:
        _progress(progress, 70, "Matching bounded-autonomy capability evidence")
        acquisition = analyze_capability_acquisition(audit)

    discovery = None
    if active.product_discovery:
        _progress(progress, 78, "Ranking evidence-backed product opportunities")
        discovery = discover_products(
            audit,
            DiscoveryConfig(
                max_opportunities=active.max_opportunities,
                offline=True,
                market_validation=False,
                reasoning_provider="none",
            ),
            technical_truth=truth,
        )

    llm_reasoning = None
    if active.llm_profile and acquisition is not None:
        _progress(progress, 90, "Requesting optional redacted LLM interpretation")
        llm_reasoning = reason_about_acquisition(
            acquisition,
            LLMReasoningConfig(profile=active.llm_profile),
        )

    _progress(progress, 100, "Audit complete — no scanned file was changed")
    return DashboardBundle(
        audit=audit,
        options=active,
        technical_truth=truth,
        discovery=discovery,
        acquisition=acquisition,
        llm_reasoning=llm_reasoning,
        entitlement=entitlement,
    )


def validate_report_output(target: Path, output: Path) -> Path:
    """Require every dashboard export to remain outside the scanned estate."""

    resolved_target = target.expanduser().resolve()
    resolved_output = output.expanduser().resolve()
    if resolved_output == resolved_target or resolved_output.is_relative_to(resolved_target):
        raise ValueError(
            "report output must be outside the scanned target so the estate remains read-only"
        )
    return resolved_output


def export_dashboard_bundle(
    bundle: DashboardBundle,
    output: Path,
    decisions: Mapping[str, str] | None = None,
) -> list[Path]:
    """Export the canonical reports plus the dashboard's advisory cleanup plan."""

    destination = validate_report_output(bundle.audit.target, output)
    normalized = _normalize_decisions(decisions or {})
    written = write_reports(bundle.audit, destination)
    if bundle.technical_truth is not None:
        written.extend(write_technical_truth_reports(bundle.technical_truth, destination))
    if bundle.discovery is not None:
        written.extend(write_product_reports(bundle.discovery, destination))
    if bundle.acquisition is not None:
        written.extend(write_acquisition_reports(bundle.acquisition, destination))
    if bundle.llm_reasoning is not None:
        written.extend(write_llm_reports(bundle.llm_reasoning, destination))

    plan_path = destination / "cleanup-plan.json"
    plan_path.write_text(
        json.dumps(
            redact_structure(build_cleanup_plan(bundle, normalized)),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    written.append(plan_path)
    return written


def candidate_key(kind: str, path: str) -> str:
    return f"{kind}:{path}"


def build_cleanup_plan(
    bundle: DashboardBundle,
    decisions: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Create deterministic, advisory-only decision metadata."""

    normalized = _normalize_decisions(decisions or {})
    known = _candidate_index(bundle.audit)
    items = []
    for key, decision in sorted(normalized.items()):
        candidate = known.get(key)
        items.append(
            {
                "candidate_key": key,
                "decision": decision,
                "path": candidate.path if candidate else key.partition(":")[2],
                "source_recommendation": candidate.kind if candidate else "custom",
                "reason": candidate.reason if candidate else "User-authored dashboard decision.",
                "confidence": candidate.confidence if candidate else "user",
                "project_root": candidate.project_root if candidate else None,
            }
        )
    return {
        "schema_version": "1.0",
        "advisory_only": True,
        "target_name": bundle.audit.target.name,
        "safety": {
            "files_modified": False,
            "files_moved": False,
            "files_deleted": False,
            "source_executed": False,
        },
        "decision_counts": {
            decision: sum(item["decision"] == decision for item in items)
            for decision in sorted(VALID_DECISIONS)
        },
        "decisions": items,
    }


def _candidate_index(audit: AuditResult) -> dict[str, Candidate]:
    groups = (
        ("extract", audit.extract_candidates),
        ("archive", audit.archive_candidates),
        ("delete-review", audit.delete_candidates),
    )
    return {
        candidate_key(kind, candidate.path): candidate
        for kind, candidates in groups
        for candidate in candidates
    }


def _normalize_decisions(decisions: Mapping[str, str]) -> dict[str, str]:
    normalized = {}
    for key, value in decisions.items():
        decision = value.strip().lower()
        if decision not in VALID_DECISIONS:
            raise ValueError(
                f"unsupported decision {value!r}; expected one of "
                f"{', '.join(sorted(VALID_DECISIONS))}"
            )
        normalized[str(key)] = decision
    return normalized


def _progress(callback: ProgressCallback | None, value: int, message: str) -> None:
    if callback is not None:
        callback(value, message)
