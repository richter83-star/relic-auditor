from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from relic_auditor.llm.health import load_provider_health, save_provider_health


def test_provider_runtime_health_persists_failure_and_redacts_secrets(
    tmp_path: Path,
) -> None:
    path = tmp_path / "provider-health.json"
    saved = save_provider_health(
        "claude-code",
        "failed",
        "timed out with token sk-abcdefghijklmnop",
        path=path,
        now=datetime(2026, 8, 15, 12, tzinfo=UTC),
    )
    assert saved.status == "failed"
    assert "sk-abcdefghijklmnop" not in saved.message
    loaded = load_provider_health("claude-code", path)
    assert loaded.status == "failed"
    assert loaded.checked_at == "2026-08-15T12:00:00Z"
    assert "sk-abcdefghijklmnop" not in path.read_text(encoding="utf-8")


def test_invalid_health_file_fails_to_unknown(tmp_path: Path) -> None:
    path = tmp_path / "provider-health.json"
    path.write_text(json.dumps({"claude-code": {"status": "ready"}}), encoding="utf-8")
    assert load_provider_health("claude-code", path).status == "unknown"
