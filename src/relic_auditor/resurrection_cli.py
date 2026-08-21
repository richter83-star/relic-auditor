from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .audit import audit_estate
from .models import ScanLimits
from .resurrection import (
    ResurrectionConfig,
    format_resurrection_console,
    resurrect_estate,
    write_resurrection_reports,
)
from .technical_truth import TechnicalTruthConfig, analyze_technical_truth


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="relic resurrect",
        description=(
            "Extract deterministic substantive subgraphs and produce a salvageable "
            "product plan or a forced TOSS_IT verdict without modifying the target."
        ),
    )
    parser.add_argument("target", type=Path, help="file, folder, or ZIP archive to inspect")
    parser.add_argument("-o", "--output", type=Path, help="report directory")
    parser.add_argument("--include-hidden", action="store_true")
    parser.add_argument("--min-nodes", type=int, default=3)
    parser.add_argument("--min-anchors", type=int, default=1)
    parser.add_argument("--max-file-mb", type=int, default=10, metavar="MB")
    parser.add_argument("--max-zip-members", type=int, default=20_000, metavar="N")
    parser.add_argument("--technical-max-file-mb", type=int, default=2)
    parser.add_argument("--max-graph-nodes", type=int, default=100_000)
    parser.add_argument("--workflow-depth", type=int, default=12)
    parser.add_argument("--max-data-flow-edges", type=int, default=50_000)
    parser.add_argument("--no-technical-cache", action="store_true")
    parser.add_argument("--technical-cache", type=Path)
    parser.add_argument(
        "--llm-profile",
        help="optional configured Relic LLM profile for bounded Phase 2 reasoning",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if (
        args.max_file_mb <= 0
        or args.max_zip_members <= 0
        or args.min_nodes <= 0
        or args.min_anchors < 0
        or args.technical_max_file_mb <= 0
        or args.max_graph_nodes <= 0
        or args.workflow_depth <= 0
        or args.max_data_flow_edges <= 0
    ):
        parser.error("scan and graph limits must be positive; --min-anchors may be zero")

    target = args.target.expanduser().resolve()
    output = (
        args.output or target.parent / f"{target.name}-relic-resurrection"
    ).expanduser().resolve()

    try:
        if target == output or (target.is_dir() and output.is_relative_to(target)):
            raise ValueError(
                "output must be outside the target so the scanned estate remains read-only"
            )

        audit_result = audit_estate(
            target,
            limits=ScanLimits(
                max_file_bytes=args.max_file_mb * 1024 * 1024,
                max_zip_members=args.max_zip_members,
            ),
            include_hidden=args.include_hidden,
        )
        truth_result = analyze_technical_truth(
            audit_result,
            TechnicalTruthConfig(
                max_file_size=args.technical_max_file_mb * 1024 * 1024,
                max_graph_nodes=args.max_graph_nodes,
                workflow_depth=args.workflow_depth,
                cache_path=str(
                    (
                        args.technical_cache
                        or output / ".relic-cache" / "technical-truth.json"
                    ).resolve()
                ),
                use_persistent_cache=not args.no_technical_cache,
                max_data_flow_edges=args.max_data_flow_edges,
            ),
        )
        resurrection_result = resurrect_estate(
            audit_result,
            truth_result,
            ResurrectionConfig(
                min_subgraph_nodes=args.min_nodes,
                min_surface_anchors=args.min_anchors,
                llm_profile=args.llm_profile,
                offline=not bool(args.llm_profile),
            ),
        )
        written = list(write_resurrection_reports(resurrection_result, output).values())
    except (
        FileNotFoundError,
        NotADirectoryError,
        PermissionError,
        KeyError,
        RuntimeError,
        ValueError,
        OSError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(format_resurrection_console(resurrection_result))
    for path in written:
        print(path)
    return 0
