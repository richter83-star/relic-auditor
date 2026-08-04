from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


SUPPORTED_PROTOCOLS = frozenset(
    {"openai-responses", "openai-chat", "anthropic-messages", "claude-code"}
)
SUPPORTED_AUTH_MODES = frozenset({"api-key", "oauth", "claude-subscription"})
SUPPORTED_CLAUDE_EFFORTS = frozenset({"low", "medium", "high"})


@dataclass(frozen=True)
class LLMProfile:
    """Non-secret connection metadata for one reasoning provider."""

    name: str
    protocol: str
    model: str
    base_url: str
    auth_mode: str = "api-key"
    api_key_env: str | None = None
    authorization_url: str | None = None
    token_url: str | None = None
    client_id: str | None = None
    scopes: tuple[str, ...] = ()
    audience: str | None = None
    effort: str | None = None

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("LLM profile name cannot be empty")
        if self.protocol not in SUPPORTED_PROTOCOLS:
            raise ValueError(f"unsupported LLM protocol: {self.protocol}")
        if self.auth_mode not in SUPPORTED_AUTH_MODES:
            raise ValueError(f"unsupported LLM auth mode: {self.auth_mode}")
        if not self.model.strip():
            raise ValueError("LLM model cannot be empty")
        if self.protocol == "claude-code":
            if self.auth_mode != "claude-subscription":
                raise ValueError(
                    "claude-code profiles require --auth claude-subscription"
                )
            if self.base_url:
                raise ValueError(
                    "claude-code profiles never use a base URL; the local "
                    "Claude Code CLI is the only endpoint"
                )
            if self.effort is not None and self.effort not in SUPPORTED_CLAUDE_EFFORTS:
                raise ValueError(
                    "claude-code effort must be one of: "
                    + ", ".join(sorted(SUPPORTED_CLAUDE_EFFORTS))
                )
            return
        if self.auth_mode == "claude-subscription":
            raise ValueError(
                "claude-subscription authentication is only valid with the "
                "claude-code protocol"
            )
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("LLM base URL must use http or https")
        _require_secure_url(self.base_url, "LLM base URL")
        if self.auth_mode == "api-key" and not self.api_key_env:
            raise ValueError("API-key profiles require an environment variable name")
        if self.auth_mode == "oauth":
            missing = [
                label
                for label, value in (
                    ("authorization_url", self.authorization_url),
                    ("token_url", self.token_url),
                    ("client_id", self.client_id),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "OAuth profiles require " + ", ".join(missing)
                )
            _require_secure_url(str(self.authorization_url), "OAuth authorization URL")
            _require_secure_url(str(self.token_url), "OAuth token URL")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "protocol": self.protocol,
            "model": self.model,
            "base_url": self.base_url,
            "auth_mode": self.auth_mode,
            "api_key_env": self.api_key_env,
            "authorization_url": self.authorization_url,
            "token_url": self.token_url,
            "client_id": self.client_id,
            "scopes": list(self.scopes),
            "audience": self.audience,
            "effort": self.effort,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "LLMProfile":
        profile = cls(
            name=str(value["name"]),
            protocol=str(value["protocol"]),
            model=str(value["model"]),
            base_url=str(value.get("base_url") or ""),
            auth_mode=str(value.get("auth_mode", "api-key")),
            api_key_env=_optional_string(value.get("api_key_env")),
            authorization_url=_optional_string(value.get("authorization_url")),
            token_url=_optional_string(value.get("token_url")),
            client_id=_optional_string(value.get("client_id")),
            scopes=tuple(str(item) for item in value.get("scopes", [])),
            audience=_optional_string(value.get("audience")),
            effort=_optional_string(value.get("effort")),
        )
        profile.validate()
        return profile


@dataclass(frozen=True)
class LLMReasoningConfig:
    profile: str
    max_input_chars: int = 40_000
    max_output_tokens: int = 2_000
    timeout_seconds: float = 90.0

    def validate(self) -> None:
        if not self.profile.strip():
            raise ValueError("LLM profile cannot be empty")
        if self.max_input_chars <= 0 or self.max_output_tokens <= 0:
            raise ValueError("LLM reasoning limits must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("LLM timeout must be positive")


@dataclass
class LLMReasoningResult:
    profile: str
    protocol: str
    model: str
    auth_mode: str
    status: str
    prompt_sha256: str
    input_chars: int
    narrative: str
    analysis: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    effort: str | None = None
    prompt_truncated: bool = False
    evidence_record_count: int = 0


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_secure_url(value: str, label: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return
    raise ValueError(f"{label} must use HTTPS unless it targets localhost")
