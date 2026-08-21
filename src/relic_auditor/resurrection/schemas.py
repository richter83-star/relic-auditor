from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResurrectionConfig:
    enabled: bool = True
    min_subgraph_nodes: int = 3
    min_surface_anchors: int = 1
    llm_profile: str | None = None
    offline: bool = True
    max_input_chars: int = 40_000
    max_output_tokens: int = 2_000
    timeout_seconds: float = 90.0
    require_citation_grounding: bool = True
    include_market_facts: bool = True

    def validate(self) -> None:
        if self.min_subgraph_nodes <= 0:
            raise ValueError("minimum subgraph nodes must be positive")
        if self.min_surface_anchors < 0:
            raise ValueError("minimum surface anchors cannot be negative")
        if self.max_input_chars <= 0 or self.max_output_tokens <= 0:
            raise ValueError("Resurrection LLM limits must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("Resurrection LLM timeout must be positive")


@dataclass
class MarketContext:
    status: str  # "live_market_verified" | "offline_heuristic" | "unavailable"
    target_category: str
    active_competitors: list[dict[str, str]]
    pricing_benchmarks: list[str]
    demand_signals: list[str]
    market_risks: list[str]
    sources: list[str]
    epistemic_rating: str = "external_market_speculation"


@dataclass
class SubstantiveSubgraph:
    subgraph_id: str
    project_family_id: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    surface_anchors: list[dict[str, Any]]
    persistence_sinks: list[dict[str, Any]]
    output_sinks: list[dict[str, Any]]
    entry_points: list[str]
    substantive_paths: list[str]
    integrity_ratio: float


@dataclass
class GateResult:
    verdict: str  # "PROCEED_TO_REASONING" | "TOSS_IT"
    reason: str
    explanation: str
    bypass_llm: bool
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class CitationVerification:
    valid: bool
    verified_citations: list[dict[str, Any]]
    ungrounded_claims: list[str]
    notes: str


@dataclass
class ResurrectionBlueprint:
    salvageable_core_paths: list[str]
    cut_list: list[str]
    missing_bridge_components: list[str]
    remediation_steps: list[str]


@dataclass
class ResurrectionResult:
    verdict: str  # "RESURRECT" | "TOSS_IT"
    verdict_confidence: float
    gate: GateResult
    subgraphs: list[SubstantiveSubgraph]
    epistemic_breakdown: dict[str, Any]
    verdict_rationale: str
    blueprint: ResurrectionBlueprint | None
    citations: list[dict[str, Any]]
    citation_verification: CitationVerification | None
    limitations: list[str]
    market_context: MarketContext | None = None
