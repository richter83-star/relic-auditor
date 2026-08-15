from __future__ import annotations

import hashlib
import os
import shutil
import stat
from pathlib import Path, PurePosixPath
from typing import Any

from ..build_packs.canonical import normalized_relative_path
from .schemas import SupervisorError


def safe_workspace_path(root: Path, relative: str) -> Path:
    normalized = normalized_relative_path(relative)
    resolved_root = root.resolve()
    current = resolved_root
    parts = PurePosixPath(normalized).parts
    for part in parts[:-1]:
        current = current / part
        if current.exists():
            if current.is_symlink() or not current.is_dir():
                raise SupervisorError("workspace path crosses a non-directory or symbolic link")
            resolved = current.resolve()
            if resolved != resolved_root and not resolved.is_relative_to(resolved_root):
                raise SupervisorError("workspace path escapes the isolated workspace")
        else:
            current.mkdir()
        if current.is_symlink():
            raise SupervisorError("workspace path crosses a symbolic link")
    candidate = resolved_root.joinpath(*parts)
    resolved = candidate.resolve(strict=False)
    if resolved != resolved_root and not resolved.is_relative_to(resolved_root):
        raise SupervisorError("workspace path escapes the isolated workspace")
    if candidate.is_symlink():
        raise SupervisorError("workspace destination is a symbolic link")
    return candidate


def hash_file(path: Path) -> str:
    digestor = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digestor.update(chunk)
    return digestor.hexdigest()


def file_manifest(root: Path, *, max_files: int = 10_000, max_bytes: int = 500 * 1024 * 1024) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    total = 0
    if not root.exists():
        return result
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise SupervisorError("workspace contains a symbolic link")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative.startswith(".relic/runtime/"):
            continue
        size = path.stat().st_size
        total += size
        if len(result) >= max_files or total > max_bytes:
            raise SupervisorError("workspace exceeds configured snapshot limits")
        result[relative] = {"sha256": hash_file(path), "size": size}
    return result


def manifest_diff(before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]) -> dict[str, Any]:
    before_paths = set(before)
    after_paths = set(after)
    return {
        "added": sorted(after_paths - before_paths),
        "deleted": sorted(before_paths - after_paths),
        "modified": sorted(path for path in before_paths & after_paths if before[path] != after[path]),
        "before": before,
        "after": after,
    }


def copy_verified_tree(source: Path, destination: Path, *, max_files: int = 10_000, max_bytes: int = 500 * 1024 * 1024) -> None:
    if not source.is_dir():
        raise SupervisorError("source tree is missing")
    count = 0
    total = 0
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source).as_posix()
        if path.is_symlink():
            raise SupervisorError("source tree contains a symbolic link")
        target = safe_workspace_path(destination, relative)
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise SupervisorError("source tree contains a non-regular file")
        count += 1
        total += info.st_size
        if count > max_files or total > max_bytes:
            raise SupervisorError("source tree exceeds configured copy limits")
        target.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            with os.fdopen(descriptor, "rb", closefd=False) as incoming, target.open("xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
        finally:
            os.close(descriptor)
