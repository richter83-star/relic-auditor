from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .auth import SecretStore, access_token
from .schemas import LLMProfile


JSONTransport = Callable[
    [str, dict[str, str], dict[str, Any], float], dict[str, Any]
]


def complete(
    profile: LLMProfile,
    prompt: str,
    *,
    max_output_tokens: int,
    timeout_seconds: float,
    transport: JSONTransport | None = None,
    secret_store: SecretStore | None = None,
    claude_runner: "Any | None" = None,
) -> str:
    profile.validate()
    if profile.protocol == "claude-code":
        from . import claude_code

        return claude_code.complete_text(
            profile,
            prompt,
            timeout_seconds=timeout_seconds,
            runner=claude_runner,
        )
    headers = _authorization_headers(profile, secret_store)
    sender = transport or _post_json
    if profile.protocol == "openai-responses":
        endpoint = _endpoint(profile.base_url, "responses")
        payload = {
            "model": profile.model,
            "input": prompt,
            "max_output_tokens": max_output_tokens,
        }
        response = sender(endpoint, headers, payload, timeout_seconds)
        return _openai_responses_text(response)
    if profile.protocol == "openai-chat":
        endpoint = _endpoint(profile.base_url, "chat/completions")
        payload = {
            "model": profile.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_output_tokens,
            "temperature": 0,
        }
        response = sender(endpoint, headers, payload, timeout_seconds)
        return _openai_chat_text(response)
    if profile.protocol == "anthropic-messages":
        endpoint = _endpoint(profile.base_url, "messages")
        headers["anthropic-version"] = "2023-06-01"
        payload = {
            "model": profile.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_output_tokens,
            "temperature": 0,
        }
        response = sender(endpoint, headers, payload, timeout_seconds)
        return _anthropic_text(response)
    raise ValueError(f"unsupported LLM protocol: {profile.protocol}")


def _authorization_headers(
    profile: LLMProfile, secret_store: SecretStore | None
) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "relic-auditor/0.8",
    }
    if profile.auth_mode == "oauth":
        headers["Authorization"] = (
            f"Bearer {access_token(profile, store=secret_store)}"
        )
        return headers
    key = os.environ.get(str(profile.api_key_env), "")
    if not key:
        raise RuntimeError(
            f"API key environment variable is not set: {profile.api_key_env}"
        )
    if profile.protocol == "anthropic-messages":
        headers["x-api-key"] = key
    else:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _endpoint(base_url: str, suffix: str) -> str:
    return f"{base_url.rstrip('/')}/{suffix.lstrip('/')}"


def _post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"LLM provider returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"LLM provider connection failed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("LLM provider returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("LLM provider returned a non-object response")
    return value


def _openai_responses_text(value: dict[str, Any]) -> str:
    direct = value.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    parts = []
    for output in value.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return _require_text(parts)


def _openai_chat_text(value: dict[str, Any]) -> str:
    try:
        content = value["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("OpenAI-compatible response contained no message") from exc
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        return _require_text(
            item.get("text", "")
            for item in content
            if isinstance(item, dict)
        )
    raise RuntimeError("OpenAI-compatible response contained no text")


def _anthropic_text(value: dict[str, Any]) -> str:
    return _require_text(
        item.get("text", "")
        for item in value.get("content", [])
        if isinstance(item, dict) and item.get("type") == "text"
    )


def _require_text(values: Any) -> str:
    text = "\n".join(str(item) for item in values if str(item).strip()).strip()
    if not text:
        raise RuntimeError("LLM provider returned no text")
    return text
