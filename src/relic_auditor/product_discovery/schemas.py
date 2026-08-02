from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class DiscoveryConfig:
    enabled: bool = True
    max_opportunities: int = 6
    offline: bool = True
    market_validation: bool = False
    reasoning_provider: str = "none"
    minimum_evidence_score: int = 35
    maximum_sampled_source_size: int = 32 * 1024
    require_secret_redaction: bool = True
    industry_hints: tuple[str, ...] = ()
    owner_skills: tuple[str, ...] = ()
    preferred_business_models: tuple[str, ...] = ()
    excluded_markets: tuple[str, ...] = ()
    regulatory_risk_tolerance: str = "medium"
    maximum_extraction_effort: str = "very high"
    allow_cross_project: bool = True


@dataclass
class DiscoveryResult:
    intent: dict[str, Any]
    capabilities: list[dict[str, Any]]
    opportunities: list[dict[str, Any]]
    evidence_index: list[dict[str, Any]]
    extraction_plans: list[dict[str, Any]]
    market_validation: dict[str, Any]
    project_families: list[dict[str, Any]]
    rejected_candidates: list[dict[str, Any]] = field(default_factory=list)


class ReasoningProvider(Protocol):
    name: str

    def enrich(self, redacted_context: dict[str, Any]) -> dict[str, Any]:
        """Return bounded enrichments without filesystem access."""
