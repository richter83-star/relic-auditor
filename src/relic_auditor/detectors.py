from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import PurePosixPath

from .models import FileRecord, ProjectRecord


MANIFEST_NAMES = frozenset(
    {
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "Pipfile",
        "setup.py",
        "setup.cfg",
        "poetry.lock",
        "pnpm-workspace.yaml",
        "turbo.json",
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
    }
)

HIGH_SIGNAL_NAMES = frozenset(
    {
        "README.md",
        "README.rst",
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "docker-compose.yml",
        "docker-compose.yaml",
        "Dockerfile",
        "next.config.js",
        "next.config.mjs",
        "next.config.ts",
        "vite.config.js",
        "vite.config.ts",
        "tsconfig.json",
        ".env.example",
        "schema.prisma",
    }
)

SOURCE_EXTENSIONS = frozenset(
    {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs"}
)


def project_root_for(path: str, manifest_roots: set[str]) -> str | None:
    pure = PurePosixPath(path)
    parents = [str(p) for p in (pure.parent, *pure.parents)]
    matches = [root for root in manifest_roots if root == "." or root in parents]
    return max(matches, key=lambda value: len(PurePosixPath(value).parts), default=None)


def detect_projects(files: list[FileRecord]) -> list[ProjectRecord]:
    roots: dict[str, dict[str, object]] = defaultdict(
        lambda: {"kinds": set(), "signals": set(), "manifests": set()}
    )

    for record in files:
        path = PurePosixPath(record.path)
        name = path.name
        parent = str(path.parent) if str(path.parent) else "."
        if name not in MANIFEST_NAMES and not name.startswith("next.config."):
            continue

        info = roots[parent]
        info["manifests"].add(record.path)  # type: ignore[union-attr]
        if name == "package.json":
            info["kinds"].add("Node.js")  # type: ignore[union-attr]
            info["signals"].add("package.json")  # type: ignore[union-attr]
            _add_node_signals(record.text, info)
        elif name in {"pyproject.toml", "requirements.txt", "Pipfile", "setup.py", "setup.cfg", "poetry.lock"}:
            info["kinds"].add("Python")  # type: ignore[union-attr]
            info["signals"].add(name)  # type: ignore[union-attr]
            if record.text and re.search(r"(?im)^\s*fastapi(?:\s|[=<>~!\[])", record.text):
                info["kinds"].add("FastAPI")  # type: ignore[union-attr]
                info["signals"].add(f"{name} declares FastAPI")  # type: ignore[union-attr]
        elif name.startswith("next.config."):
            info["kinds"].update({"Node.js", "Next.js"})  # type: ignore[union-attr]
            info["signals"].add(name)  # type: ignore[union-attr]
        elif name.startswith("docker-compose"):
            info["kinds"].add("Docker Compose")  # type: ignore[union-attr]
            info["signals"].add(name)  # type: ignore[union-attr]
        elif name == "Dockerfile":
            info["kinds"].add("Docker")  # type: ignore[union-attr]
            info["signals"].add(name)  # type: ignore[union-attr]

    manifest_roots = set(roots)
    for record in files:
        if record.extension != ".py" or not record.text:
            continue
        if not re.search(r"(?m)^\s*(?:from\s+fastapi\s+import|import\s+fastapi\b)", record.text):
            continue
        root = project_root_for(record.path, manifest_roots)
        if root is None:
            root = str(PurePosixPath(record.path).parent)
            manifest_roots.add(root)
        roots[root]["kinds"].update({"Python", "FastAPI"})  # type: ignore[union-attr]
        roots[root]["signals"].add(f"{record.path} imports FastAPI")  # type: ignore[union-attr]

    projects: list[ProjectRecord] = []
    for root, info in sorted(roots.items()):
        scoped = [record for record in files if _is_beneath(record.path, root)]
        projects.append(
            ProjectRecord(
                root=root,
                kinds=sorted(info["kinds"]),  # type: ignore[arg-type]
                signals=sorted(info["signals"]),  # type: ignore[arg-type]
                manifests=sorted(info["manifests"]),  # type: ignore[arg-type]
                source_files=sum(record.extension in SOURCE_EXTENSIONS for record in scoped),
                test_files=sum(_is_test(record.path) for record in scoped),
                documentation_files=sum(
                    PurePosixPath(record.path).suffix.lower() in {".md", ".rst"} for record in scoped
                ),
            )
        )
    return projects


def classify_role(path: str) -> str:
    pure = PurePosixPath(path)
    name = pure.name
    parts = {part.lower() for part in pure.parts}
    if name in MANIFEST_NAMES or name in {"tsconfig.json", "schema.prisma"}:
        return "manifest/configuration"
    if _is_test(path):
        return "test"
    if pure.suffix.lower() in {".md", ".rst"}:
        return "documentation"
    if "migrations" in parts:
        return "database migration"
    if "api" in parts or "routes" in parts or "routers" in parts:
        return "API/routing"
    if "components" in parts or pure.suffix.lower() in {".jsx", ".tsx"}:
        return "UI/component"
    if "models" in parts or name in {"schema.py", "schema.ts"}:
        return "data model"
    if pure.suffix.lower() in SOURCE_EXTENSIONS:
        return "source"
    return "asset/other"


def is_high_signal(path: str) -> bool:
    pure = PurePosixPath(path)
    return (
        pure.name in HIGH_SIGNAL_NAMES
        or pure.name.startswith("next.config.")
        or pure.name in {"main.py", "app.py", "server.py", "index.ts", "index.js"}
        or "schema" in pure.stem.lower()
    )


def _add_node_signals(text: str | None, info: dict[str, object]) -> None:
    if not text:
        return
    try:
        package = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        info["signals"].add("package.json could not be parsed")  # type: ignore[union-attr]
        return
    dependencies = {}
    dependencies.update(package.get("dependencies") or {})
    dependencies.update(package.get("devDependencies") or {})
    mappings = {
        "next": "Next.js",
        "react": "React",
        "express": "Express",
        "fastify": "Fastify",
        "@nestjs/core": "NestJS",
        "electron": "Electron",
    }
    for dependency, kind in mappings.items():
        if dependency in dependencies:
            info["kinds"].add(kind)  # type: ignore[union-attr]
            info["signals"].add(f"package.json declares {dependency}")  # type: ignore[union-attr]


def _is_beneath(path: str, root: str) -> bool:
    if root == ".":
        return True
    return path == root or path.startswith(f"{root}/")


def _is_test(path: str) -> bool:
    pure = PurePosixPath(path)
    lower = path.lower()
    return (
        "tests" in {part.lower() for part in pure.parts}
        or pure.name.startswith("test_")
        or ".test." in lower
        or ".spec." in lower
    )
