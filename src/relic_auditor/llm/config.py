from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .schemas import LLMProfile


def config_directory() -> Path:
    override = os.environ.get("RELIC_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home()))
        return root / "Relic Auditor"
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "relic-auditor"


class ProfileStore:
    """Stores only non-secret profile metadata."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or config_directory() / "llm-profiles.json").expanduser()

    def list(self) -> list[LLMProfile]:
        values = self._read().get("profiles", [])
        profiles = [LLMProfile.from_dict(item) for item in values]
        return sorted(profiles, key=lambda item: item.name.lower())

    def get(self, name: str) -> LLMProfile:
        for profile in self.list():
            if profile.name == name:
                return profile
        raise KeyError(f"LLM profile not found: {name}")

    def save(self, profile: LLMProfile) -> None:
        profile.validate()
        profiles = {item.name: item for item in self.list()}
        profiles[profile.name] = profile
        self._write(
            {
                "schema_version": "1.0",
                "profiles": [
                    item.to_dict()
                    for item in sorted(
                        profiles.values(), key=lambda value: value.name.lower()
                    )
                ],
            }
        )

    def remove(self, name: str) -> bool:
        profiles = {item.name: item for item in self.list()}
        existed = profiles.pop(name, None) is not None
        if existed:
            self._write(
                {
                    "schema_version": "1.0",
                    "profiles": [
                        item.to_dict()
                        for item in sorted(
                            profiles.values(), key=lambda value: value.name.lower()
                        )
                    ],
                }
            )
        return existed

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": "1.0", "profiles": []}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("profiles"), list):
            raise ValueError(f"invalid LLM profile file: {self.path}")
        return value

    def _write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(self.path)
