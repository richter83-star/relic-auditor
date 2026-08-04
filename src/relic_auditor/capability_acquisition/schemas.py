from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AcquisitionConfig:
    max_evidence_per_match: int = 8
    max_candidates: int = 40
    minimum_signal_score: float = 0.18

    def validate(self) -> None:
        if self.max_evidence_per_match <= 0 or self.max_candidates <= 0:
            raise ValueError("acquisition limits must be positive")
        if not 0.0 <= self.minimum_signal_score <= 1.0:
            raise ValueError("minimum_signal_score must be between 0 and 1")


@dataclass(frozen=True)
class CapabilityEvidence:
    path: str
    line: int
    signal: str
    matched: str
    excerpt: str
    weight: float
    source: str


@dataclass
class CapabilityMatch:
    capability: str
    title: str
    confidence: float
    confidence_label: str
    evidence: list[CapabilityEvidence] = field(default_factory=list)
    context: str = "source"
    reusable: bool = False


@dataclass
class ItemAssessment:
    path: str
    source: str
    role: str | None
    size: int
    inspected: bool
    confidence: float
    capability_matches: list[CapabilityMatch] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class AcquisitionResult:
    target: Path
    items: list[ItemAssessment]
    capability_summary: list[dict[str, Any]]
    best_candidates: list[dict[str, Any]]
    missing_pieces: list[dict[str, Any]]
    suggested_build_path: list[dict[str, Any]]
    risk_notes: list[str]
    scan_summary: dict[str, Any]

