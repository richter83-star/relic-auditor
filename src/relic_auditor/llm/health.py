"""Persistent, non-secret provider runtime truth for the desktop UI."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..safety import redact_secrets


_STATUSES = {"unknown", "running", "operational", "failed"}


@dataclass(frozen=True)
class ProviderRuntimeHealth:
    provider: str
    status: str = "unknown"
    checked_at: str | None = None
    message: str = ""


def default_provider_health_path() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "Relic Auditor" / "provider-health.json"


def load_provider_health(
    provider: str, path: Path | None = None
) -> ProviderRuntimeHealth:
    target = path or default_provider_health_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        value = payload.get(provider, {})
    except (FileNotFoundError, OSError, json.JSONDecodeError, AttributeError):
        value = {}
    status = str(value.get("status", "unknown"))
    if status not in _STATUSES:
        status = "unknown"
    checked_at = value.get("checked_at")
    message = redact_secrets(str(value.get("message", "")))[:1000]
    return ProviderRuntimeHealth(provider, status, str(checked_at) if checked_at else None, message)


def save_provider_health(
    provider: str,
    status: str,
    message: str,
    *,
    path: Path | None = None,
    now: datetime | None = None,
) -> ProviderRuntimeHealth:
    if status not in _STATUSES - {"unknown"}:
        raise ValueError("provider runtime status is invalid")
    target = path or default_provider_health_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            payload = {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        payload = {}
    checked_at = (now or datetime.now(UTC)).astimezone(UTC).isoformat().replace(
        "+00:00", "Z"
    )
    clean = redact_secrets(str(message))[:1000]
    payload[provider] = {
        "status": status,
        "checked_at": checked_at,
        "message": clean,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, target)
    return ProviderRuntimeHealth(provider, status, checked_at, clean)
