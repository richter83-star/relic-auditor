from __future__ import annotations

from dataclasses import dataclass
from typing import Any


MIN_CONCLUSION_COVERAGE = 0.60


@dataclass(frozen=True)
class TechnicalTruthConfig:
    enabled: bool = True
    languages: tuple[str, ...] = ("auto",)
    max_file_size: int = 2 * 1024 * 1024
    max_graph_nodes: int = 100_000
    cross_project_analysis: bool = True
    workflow_depth: int = 12
    include_tests: bool = True
    include_generated_files: bool = False
    bounded_reasoning_provider: str = "none"
    cache_path: str | None = None
    use_persistent_cache: bool = True
    resolve_git_lineage: bool = True
    max_data_flow_edges: int = 50_000


@dataclass
class TechnicalTruthResult:
    summary: dict[str, Any]
    symbols: list[dict[str, Any]]
    graph: dict[str, Any]
    project_families: list[dict[str, Any]]
    surfaces: dict[str, Any]
    workflows: list[dict[str, Any]]
    capabilities: list[dict[str, Any]]
    contradictions: list[dict[str, Any]]
    reachability: list[dict[str, Any]]
    parse_results: list[dict[str, Any]]
