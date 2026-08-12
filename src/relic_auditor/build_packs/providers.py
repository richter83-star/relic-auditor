from __future__ import annotations

from typing import Any, Mapping, Protocol

from ..safety import redact_structure


class BuildPackProvider(Protocol):
    name: str

    def enrich(self, redacted_context: Mapping[str, Any]) -> Mapping[str, Any]: ...


_ALLOWED = frozenset({"assumptions", "questions", "market_hypotheses"})


def bounded_enrichment(
    provider: BuildPackProvider | None,
    context: Mapping[str, Any],
    *,
    allowed: bool,
) -> dict[str, Any]:
    if provider is None or not allowed:
        return {"status": "not_requested", "provider": "none", "content": {}}
    try:
        raw = provider.enrich(redact_structure(dict(context)))
        if not isinstance(raw, Mapping):
            raise TypeError("provider response must be an object")
        unknown = set(raw) - _ALLOWED
        if unknown:
            raise ValueError("provider returned unsupported fields")
        content: dict[str, list[str]] = {}
        for key in sorted(_ALLOWED):
            values = raw.get(key, [])
            if not isinstance(values, list) or any(
                not isinstance(value, str) for value in values
            ):
                raise ValueError("provider fields must be lists of text")
            content[key] = [value[:500] for value in values[:10]]
        return {
            "status": "complete",
            "provider": str(getattr(provider, "name", "configured"))[:80],
            "content": redact_structure(content),
        }
    except Exception:
        # Provider exception text can echo credentials. Never serialize it.
        return {
            "status": "unavailable",
            "provider": str(getattr(provider, "name", "configured"))[:80],
            "content": {},
            "reason": "Provider enrichment was unavailable; deterministic output was used.",
        }
