from __future__ import annotations

import re
from collections import defaultdict, deque
from typing import Any

from ..models import AuditResult
from ..technical_truth.adapters import stable_id
from ..technical_truth.analyzer import _is_test_path
from ..technical_truth.schemas import TechnicalTruthResult
from .schemas import GateResult, ResurrectionConfig, SubstantiveSubgraph


def extract_substantive_subgraphs(
    audit: AuditResult,
    technical_truth: TechnicalTruthResult,
) -> list[SubstantiveSubgraph]:
    """
    Extract deterministic connected subgraphs of substantive, non-stub,
    production code components.
    """
    # 1. Identify substantive production symbols (no stubs, no tests)
    substantive_symbols = {
        s["symbol_id"]: s
        for s in technical_truth.symbols
        if not s.get("stub") and not _is_test_path(s.get("file", ""))
    }
    substantive_ids = set(substantive_symbols.keys())

    # 2. Identify surface anchor nodes and persistence/output sinks
    surface_nodes = {}
    for cat, items in technical_truth.surfaces.items():
        if cat in {"risk_indicators", "tests"}:
            continue
        for item in items:
            surface_id = item.get("surface_id")
            if surface_id and not item.get("mock_only") and not _is_test_path(item.get("file", "")):
                surface_nodes[surface_id] = item

    # 3. Filter graph edges connecting substantive nodes & surfaces
    all_valid_ids = substantive_ids | set(surface_nodes.keys())
    active_edges = []
    adjacency = defaultdict(set)
    reverse_adj = defaultdict(set)

    for edge in technical_truth.graph.get("edges", []):
        src, tgt = edge["source"], edge["target"]
        if src in all_valid_ids and tgt in all_valid_ids:
            active_edges.append(edge)
            adjacency[src].add(tgt)
            reverse_adj[tgt].add(src)
            # Undirected connectivity for component clustering
            adjacency[tgt].add(src)

    # 4. Find connected components
    visited = set()
    components: list[set[str]] = []

    for node_id in sorted(all_valid_ids):
        if node_id in visited:
            continue
        comp = set()
        queue = deque([node_id])
        visited.add(node_id)
        while queue:
            curr = queue.popleft()
            comp.add(curr)
            for neighbor in adjacency[curr]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        if comp:
            components.append(comp)

    # 5. Build SubstantiveSubgraph objects
    subgraphs: list[SubstantiveSubgraph] = []
    for comp in components:
        comp_substantive = [substantive_symbols[nid] for nid in comp if nid in substantive_ids]
        if not comp_substantive:
            continue

        comp_surfaces = [surface_nodes[nid] for nid in comp if nid in surface_nodes]
        comp_edges = [e for e in active_edges if e["source"] in comp and e["target"] in comp]

        # Classify surface anchors, persistence sinks, output sinks
        surface_anchors = [s for s in comp_surfaces if s.get("type") in {"endpoint", "queue_consumer", "ui_screen", "framework"}]
        persistence_sinks = [
            s for s in comp_surfaces if s.get("type") == "schema"
        ] + [
            sym for sym in comp_substantive
            if re.search(r"save|create|insert|update|commit|persist|store|repository|database|prisma|session|db", sym.get("name", ""), re.I)
        ]
        output_sinks = [
            sym for sym in comp_substantive
            if re.search(r"report|export|pdf|result|emit|deliver|respond|render|serialize|output", sym.get("name", ""), re.I)
        ]

        entry_points = [
            f"{s.get('method', '')} {s.get('route', '')}".strip() or s.get("name", "")
            for s in surface_anchors
        ]

        paths = sorted({sym["file"] for sym in comp_substantive})
        family_id = comp_substantive[0].get("project_family_id", "family_unknown")

        total_refs = sum(len(sym.get("parameters", [])) + 1 for sym in comp_substantive)
        integrity_ratio = round(min(1.0, len(comp_edges) / max(1, len(comp_substantive))), 2)

        subgraph_id = stable_id("subgraph", family_id, *sorted(s["symbol_id"] for s in comp_substantive[:5]))

        subgraphs.append(
            SubstantiveSubgraph(
                subgraph_id=subgraph_id,
                project_family_id=family_id,
                nodes=comp_substantive,
                edges=comp_edges,
                surface_anchors=surface_anchors,
                persistence_sinks=persistence_sinks,
                output_sinks=output_sinks,
                entry_points=[ep for ep in entry_points if ep],
                substantive_paths=paths,
                integrity_ratio=integrity_ratio,
            )
        )

    # Sort largest/most-connected first
    subgraphs.sort(key=lambda sg: (-len(sg.nodes), -len(sg.surface_anchors), sg.subgraph_id))
    return subgraphs


def evaluate_salvageability_gate(
    subgraphs: list[SubstantiveSubgraph],
    config: ResurrectionConfig | None = None,
) -> GateResult:
    """
    Evaluate whether the codebase possesses enough connected substance
    to proceed to LLM product reasoning or if it should receive an immediate
    deterministic 'TOSS_IT' verdict.
    """
    cfg = config or ResurrectionConfig()

    if not subgraphs:
        return GateResult(
            verdict="TOSS_IT",
            reason="NO_SUBSTANTIVE_GRAPH",
            explanation="Zero connected, non-stub functional paths exist in the codebase. All code is either stubs, tests, mocks, or isolated fragments.",
            bypass_llm=True,
            metrics={"max_subgraph_nodes": 0, "max_surface_anchors": 0, "subgraph_count": 0},
        )

    largest = subgraphs[0]
    node_count = len(largest.nodes)
    anchor_count = len(largest.surface_anchors)

    if node_count < cfg.min_subgraph_nodes:
        return GateResult(
            verdict="TOSS_IT",
            reason="INSUFFICIENT_SUBSTANTIVE_NODES",
            explanation=f"Largest connected substantive subgraph contains only {node_count} non-stub symbol(s) (minimum required: {cfg.min_subgraph_nodes}). Code volume is too sparse to constitute a salvageable product core.",
            bypass_llm=True,
            metrics={"max_subgraph_nodes": node_count, "max_surface_anchors": anchor_count, "subgraph_count": len(subgraphs)},
        )

    if anchor_count < cfg.min_surface_anchors and node_count < 6:
        return GateResult(
            verdict="TOSS_IT",
            reason="NO_SURFACE_ANCHORS_OR_INTEGRATION",
            explanation=f"Substantive subgraph has {node_count} symbols but zero verified entry points or surface triggers. It represents disconnected helper routines rather than a standalone product engine.",
            bypass_llm=True,
            metrics={"max_subgraph_nodes": node_count, "max_surface_anchors": anchor_count, "subgraph_count": len(subgraphs)},
        )

    return GateResult(
        verdict="PROCEED_TO_REASONING",
        reason="SUBSTANTIVE_CORE_VERIFIED",
        explanation=f"Deterministic reachability verified a connected substantive subgraph of {node_count} symbols and {anchor_count} surface anchor(s).",
        bypass_llm=False,
        metrics={"max_subgraph_nodes": node_count, "max_surface_anchors": anchor_count, "subgraph_count": len(subgraphs)},
    )
