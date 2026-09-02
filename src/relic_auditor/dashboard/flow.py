from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .core import DashboardBundle


class FlowState(str, Enum):
    """Authoritative states in the focused product journey."""

    NO_TARGET = "no_target"
    TARGET_SELECTED = "target_selected"
    SCANNING = "scanning"
    ANSWER_READY = "answer_ready"
    OPPORTUNITY_CHOOSER = "opportunity_chooser"
    OPPORTUNITY_SELECTED = "opportunity_selected"
    PREPARE_PRODUCT = "prepare_product"
    BUILD_PACK_GATE = "build_pack_gate"
    BUILD_PACK_READY = "build_pack_ready"
    BUILD_SESSION_ACTIVE = "build_session_active"


_ALLOWED_TRANSITIONS = {
    FlowState.NO_TARGET: {FlowState.TARGET_SELECTED},
    FlowState.TARGET_SELECTED: {FlowState.NO_TARGET, FlowState.SCANNING},
    FlowState.SCANNING: {FlowState.TARGET_SELECTED, FlowState.ANSWER_READY},
    FlowState.ANSWER_READY: {
        FlowState.NO_TARGET,
        FlowState.TARGET_SELECTED,
        FlowState.OPPORTUNITY_CHOOSER,
        FlowState.PREPARE_PRODUCT,
    },
    FlowState.OPPORTUNITY_CHOOSER: {
        FlowState.ANSWER_READY,
        FlowState.OPPORTUNITY_SELECTED,
    },
    FlowState.OPPORTUNITY_SELECTED: {
        FlowState.ANSWER_READY,
        FlowState.OPPORTUNITY_CHOOSER,
        FlowState.PREPARE_PRODUCT,
    },
    FlowState.PREPARE_PRODUCT: {
        FlowState.ANSWER_READY,
        FlowState.OPPORTUNITY_SELECTED,
        FlowState.OPPORTUNITY_CHOOSER,
        FlowState.BUILD_PACK_GATE,
        FlowState.BUILD_PACK_READY,
    },
    FlowState.BUILD_PACK_GATE: {FlowState.PREPARE_PRODUCT},
    FlowState.BUILD_PACK_READY: {
        FlowState.ANSWER_READY,
        FlowState.OPPORTUNITY_SELECTED,
        FlowState.PREPARE_PRODUCT,
        FlowState.BUILD_SESSION_ACTIVE,
    },
    FlowState.BUILD_SESSION_ACTIVE: {FlowState.BUILD_PACK_READY},
}


@dataclass
class FlowController:
    """Small state machine independent of Qt and report persistence."""

    state: FlowState = FlowState.NO_TARGET

    def transition(self, destination: FlowState, *, new_workflow: bool = False) -> None:
        if destination == self.state:
            return
        if new_workflow and destination in {
            FlowState.NO_TARGET,
            FlowState.TARGET_SELECTED,
        }:
            self.state = destination
            return
        if destination not in _ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(
                f"invalid focused-flow transition: {self.state.value} -> "
                f"{destination.value}"
            )
        self.state = destination


def product_friendly_title(title: str) -> str:
    """Present a bounded product concept without rewriting source evidence."""

    if title.strip().casefold() == "traceable compliance gap assessment":
        return "Compliance Gap Assessment Platform"
    return title


def focused_answer(
    bundle: DashboardBundle, opportunity_id: str | None = None
) -> dict[str, Any]:
    """Translate evidence into the decision-first Answer screen contract."""

    target = bundle.audit.target.name or "This project"
    opportunities = list(bundle.discovery.opportunities) if bundle.discovery else []
    lead = next(
        (
            item
            for item in opportunities
            if opportunity_id
            and str(item.get("opportunity_id") or "") == opportunity_id
        ),
        opportunities[0] if opportunities else None,
    )
    lead_assets = list(lead.get("reusable_assets", [])) if lead else []
    acquisition_assets = (
        list(bundle.acquisition.best_candidates) if bundle.acquisition else []
    )
    reusable_count = len(lead_assets) or len(acquisition_assets)
    missing = list(lead.get("missing_components", [])) if lead else []

    truth = bundle.technical_truth
    contradictions = len(truth.contradictions) if truth else 0
    incomplete = (
        sum(
            item.get("completion_status") != "verified_end_to_end"
            for item in truth.workflows
        )
        if truth
        else 0
    )
    concern_count = contradictions + incomplete + len(bundle.audit.warnings) + len(missing)

    if lead:
        strength = str(lead.get("evidence_strength") or "").casefold()
        adjective = "strong" if strength in {"strong", "high", "verified"} else "credible"
        conclusion = f"{target} has a {adjective} reusable foundation."
        detail = (
            "Relic found enough working structure to support a practical product path. "
            "The product still needs assembly and validation."
        )
        technical_title = str(lead.get("title") or "Focused product opportunity")
        opportunity_title = product_friendly_title(technical_title)
        opportunity_summary = str(
            lead.get("summary") or "The strongest evidence-backed product path."
        )
        recommendation = "Prepare this opportunity for development."
    else:
        conclusion = f"{target} contains reusable software, but no product path is ready yet."
        detail = (
            "Relic completed the appraisal without inventing a recommendation that the "
            "evidence cannot support."
        )
        opportunity_title = "No evidence-backed opportunity is ready"
        opportunity_summary = "Review the technical evidence and strengthen the incomplete workflows."
        recommendation = "Review the highest-impact missing work before preparing a product."

    if reusable_count:
        asset_word = "asset" if reusable_count == 1 else "assets"
        reusable = (
            f"{reusable_count:,} reusable {asset_word} can likely accelerate the build."
        )
    else:
        reusable = "Reusable assets need individual evidence review before they can accelerate a build."

    if concern_count:
        item_word = "item" if concern_count == 1 else "items"
        verb = "needs" if concern_count == 1 else "need"
        concerns = (
            f"{concern_count:,} incomplete, risky, missing, or review-worthy "
            f"{item_word} {verb} attention."
        )
    else:
        concerns = "No material evidence conflicts were found, but exact assets still require review."

    scope = (
        lead.get("mvp_scope")
        or lead.get("mvp_definition")
        or opportunity_summary
        if lead
        else "Resolve the missing evidence before defining an MVP."
    )
    if isinstance(scope, (list, tuple)):
        scope = "; ".join(map(str, scope))

    return {
        "conclusion": conclusion,
        "detail": detail,
        "opportunity_title": opportunity_title,
        "technical_opportunity_title": (
            str(lead.get("title") or opportunity_title) if lead else opportunity_title
        ),
        "opportunity_id": str(lead.get("opportunity_id") or "") if lead else "",
        "opportunity_summary": opportunity_summary,
        "reusable": reusable,
        "reusable_count": reusable_count,
        "concerns": concerns,
        "concern_count": concern_count,
        "recommendation": recommendation,
        "missing": [str(item) for item in missing],
        "mvp": str(scope),
        "risks": [str(item) for item in missing[:3]]
        or (["Review the technical evidence before approving reusable assets"] if lead else []),
        "opportunities": opportunities,
    }
