from __future__ import annotations

import sys

from . import cli
from . import resurrection_cli


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "resurrect":
        return resurrection_cli.main(args[1:])
    return cli.main(args)
