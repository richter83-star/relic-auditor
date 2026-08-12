from __future__ import annotations

import argparse
import stat
import zipfile
from pathlib import Path


VERSION = "0.10.0"
EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".test-support",
    ".uv-cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "releases",
}
EXCLUDED_FILES = {
    ".github/workflows/windows-installer.yml",
    "tests/test_installer_sources.py",
}
EXCLUDED_PREFIXES = {"installer/windows/"}


def source_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        if set(path.relative_to(root).parts) & EXCLUDED_PARTS:
            continue
        if relative in EXCLUDED_FILES or any(
            relative.startswith(prefix) for prefix in EXCLUDED_PREFIXES
        ):
            continue
        if relative.endswith((".pyc", ".pyo")) or ".egg-info/" in relative:
            continue
        files.append(path)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def build(root: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"relic-auditor-{VERSION}"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in source_files(root):
            relative = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(f"{prefix}/{relative}", (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(
                info,
                path.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.root.resolve(), args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
