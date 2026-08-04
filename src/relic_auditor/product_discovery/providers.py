from __future__ import annotations

from typing import Any


class DeterministicProvider:
    name = "none"

    def enrich(self, redacted_context: dict[str, Any]) -> dict[str, Any]:
        return {"status": "not_requested", "provider": self.name, "enrichments": []}


class LocalReasoningProvider:
    name = "local"

    def enrich(self, redacted_context: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "not_configured",
            "provider": self.name,
            "enrichments": [],
            "reason": "No local reasoning adapter is configured.",
        }


class ConfiguredExternalProvider:
    name = "configured_external"

    def enrich(self, redacted_context: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "not_configured",
            "provider": self.name,
            "enrichments": [],
            "reason": "External providers require an explicit adapter; repository content was not sent.",
        }


def provider_for(name: str):
    providers = {
        "none": DeterministicProvider,
        "local": LocalReasoningProvider,
        "configured_external": ConfiguredExternalProvider,
    }
    if name not in providers:
        raise ValueError(f"Unsupported reasoning provider: {name}")
    return providers[name]()
