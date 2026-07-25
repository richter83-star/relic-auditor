from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .audit import audit_estate
from .models import ScanLimits
from .reports import write_reports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="relic",
        description="Deterministically appraise a messy software estate without executing or modifying it.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit", help="scan a folder and write appraisal reports")
    audit.add_argument("target", type=Path, help="folder to inspect")
    audit.add_argument(
        "-o",
        "--output",
        type=Path,
        help="report directory (default: ./relic-report)",
    )
    audit.add_argument(
        "--include-hidden",
        action="store_true",
        help="inspect hidden files except ignored VCS/cache/dependency directories",
    )
    audit.add_argument(
        "--max-file-mb",
        type=int,
        default=10,
        metavar="MB",
        help="maximum individual file/member size to inspect (default: 10)",
    )
    audit.add_argument(
        "--max-zip-members",
        type=int,
        default=20_000,
        metavar="N",
        help="reject ZIPs with more members (default: 20000)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "audit":
        parser.error("a command is required")

    if args.max_file_mb <= 0 or args.max_zip_members <= 0:
        parser.error("scan limits must be positive")

    target = args.target.expanduser().resolve()
    default_output = target.parent / f"{target.name}-relic-report"
    output = (args.output or default_output).expanduser().resolve()
    try:
        if target == output or output.is_relative_to(target):
            print(
                "error: output must be outside the target so the scanned estate remains read-only",
                file=sys.stderr,
            )
            return 2
        result = audit_estate(
            target,
            limits=ScanLimits(
                max_file_bytes=args.max_file_mb * 1024 * 1024,
                max_zip_members=args.max_zip_members,
            ),
            include_hidden=args.include_hidden,
        )
        written = write_reports(result, output)
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Relic audit complete: {result.target}")
    print(f"Projects: {len(result.projects)} | Files observed: {len(result.files)}")
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
