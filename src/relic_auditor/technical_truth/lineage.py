from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any


def inspect_git_lineage(scan_root: Path, project_roots: list[str]) -> list[dict[str, Any]]:
    results = []
    boundary = scan_root.resolve()
    for root in sorted(set(project_roots)):
        project = boundary if root == "." else (boundary / root).resolve()
        if project != boundary and boundary not in project.parents:
            continue
        dotgit = project / ".git"
        if not dotgit.exists():
            continue
        result = {"project_root": root, "kind": "repository", "head": None, "branch": None, "remote_urls": [], "worktree_gitdir": None, "outside_boundary_not_followed": False}
        gitdir = dotgit
        if dotgit.is_file():
            result["kind"] = "worktree"
            try:
                pointer = dotgit.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                pointer = ""
            if pointer.startswith("gitdir:"):
                candidate = (project / pointer.split(":", 1)[1].strip()).resolve()
                result["worktree_gitdir"] = str(candidate)
                if candidate != boundary and boundary not in candidate.parents:
                    result["outside_boundary_not_followed"] = True
                    results.append(result)
                    continue
                gitdir = candidate
        head = _read_small(gitdir / "HEAD")
        if head:
            if head.startswith("ref:"):
                reference = head.split(":", 1)[1].strip()
                result["branch"] = reference.removeprefix("refs/heads/")
                result["head"] = _read_small(gitdir / reference) or _read_packed_ref(gitdir / "packed-refs", reference)
            else:
                result["head"] = head
        config_path = gitdir / "config"
        if config_path.exists():
            parser = configparser.ConfigParser()
            try:
                parser.read(config_path, encoding="utf-8")
                result["remote_urls"] = sorted({parser[section].get("url") for section in parser.sections() if section.startswith("remote ") and parser[section].get("url")})
            except (OSError, configparser.Error):
                pass
        results.append(result)
    return results


def _read_small(path: Path) -> str | None:
    try:
        if path.is_file() and path.stat().st_size <= 64 * 1024:
            return path.read_text(encoding="utf-8", errors="replace").strip() or None
    except OSError:
        return None
    return None


def _read_packed_ref(path: Path, reference: str) -> str | None:
    text = _read_small(path)
    if not text:
        return None
    for line in text.splitlines():
        if line.endswith(" " + reference):
            return line.split()[0]
    return None
