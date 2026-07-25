from __future__ import annotations

import re
from pathlib import PurePosixPath


IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".idea",
        ".next",
        ".nuxt",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".turbo",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "target",
        "venv",
    }
)

JUNK_FILES = frozenset(
    {
        ".DS_Store",
        "Thumbs.db",
        "desktop.ini",
        ".eslintcache",
        ".coverage",
    }
)

BINARY_EXTENSIONS = frozenset(
    {
        ".7z",
        ".a",
        ".avi",
        ".bin",
        ".bmp",
        ".class",
        ".db",
        ".dll",
        ".dmg",
        ".doc",
        ".docx",
        ".eot",
        ".exe",
        ".gif",
        ".gz",
        ".ico",
        ".jar",
        ".jpeg",
        ".jpg",
        ".lockb",
        ".mov",
        ".mp3",
        ".mp4",
        ".o",
        ".otf",
        ".pdf",
        ".png",
        ".pyc",
        ".so",
        ".sqlite",
        ".tar",
        ".tgz",
        ".ttf",
        ".wav",
        ".webm",
        ".webp",
        ".woff",
        ".woff2",
        ".xz",
    }
)

SECRET_TOKEN_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
)

SECRET_ASSIGNMENT = re.compile(
    r"""(?im)^(\s*["']?(?:api[_-]?key|apikey|secret|token|password|passwd|private[_-]?key)"""
    r"""["']?\s*[:=]\s*)(?:"[^"\n]*"|'[^'\n]*'|[^\s,#;]+)"""
)

PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END [^-]+-----"
)


def redact_secrets(value: str) -> str:
    redacted = SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", value)
    redacted = PRIVATE_KEY_BLOCK.sub("[REDACTED PRIVATE KEY]", redacted)
    for pattern in SECRET_TOKEN_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def is_binary_name(name: str) -> bool:
    return PurePosixPath(name).suffix.lower() in BINARY_EXTENSIONS


def is_safe_zip_member(name: str) -> tuple[bool, str | None]:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or "\x00" in normalized:
        return False, "empty or NUL-containing member name"
    if path.is_absolute() or re.match(r"^[A-Za-z]:", normalized):
        return False, "absolute member path"
    if ".." in path.parts:
        return False, "path traversal member"
    return True, None


def likely_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]
