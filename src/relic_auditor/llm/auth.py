from __future__ import annotations

import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import secrets
import time
from typing import Any, Callable, Protocol
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
import webbrowser

from .schemas import LLMProfile


KEYRING_SERVICE = "relic-auditor"
TokenTransport = Callable[[str, dict[str, str], float], dict[str, Any]]


class SecretStore(Protocol):
    def get(self, profile: str) -> dict[str, Any] | None: ...

    def set(self, profile: str, value: dict[str, Any]) -> None: ...

    def delete(self, profile: str) -> bool: ...


class KeyringSecretStore:
    """Persists OAuth tokens in the OS credential store, never in reports/config."""

    def __init__(self) -> None:
        try:
            import keyring
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                'OAuth storage requires the LLM extra: python -m pip install -e ".[llm]"'
            ) from exc
        self._keyring = keyring

    def get(self, profile: str) -> dict[str, Any] | None:
        raw = self._keyring.get_password(KEYRING_SERVICE, profile)
        if not raw:
            return None
        value = json.loads(raw)
        return value if isinstance(value, dict) else None

    def set(self, profile: str, value: dict[str, Any]) -> None:
        self._keyring.set_password(
            KEYRING_SERVICE,
            profile,
            json.dumps(value, separators=(",", ":"), sort_keys=True),
        )

    def delete(self, profile: str) -> bool:
        try:
            self._keyring.delete_password(KEYRING_SERVICE, profile)
        except self._keyring.errors.PasswordDeleteError:
            return False
        return True


def oauth_login(
    profile: LLMProfile,
    *,
    store: SecretStore | None = None,
    transport: TokenTransport | None = None,
    open_browser: Callable[[str], bool] = webbrowser.open,
    timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    """Run OAuth 2.0 Authorization Code + PKCE using a loopback callback."""

    profile.validate()
    if profile.auth_mode != "oauth":
        raise ValueError(f"profile {profile.name!r} is not configured for OAuth")
    secret_store = store or KeyringSecretStore()
    token_transport = transport or _post_form
    verifier = _pkce_verifier()
    challenge = _pkce_challenge(verifier)
    state = secrets.token_urlsafe(24)
    server = _CallbackServer(("127.0.0.1", 0), _CallbackHandler)
    server.timeout = min(timeout_seconds, 1.0)
    redirect_uri = f"http://127.0.0.1:{server.server_port}/callback"
    parameters = {
        "response_type": "code",
        "client_id": str(profile.client_id),
        "redirect_uri": redirect_uri,
        "scope": " ".join(profile.scopes),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if profile.audience:
        parameters["audience"] = profile.audience
    separator = "&" if "?" in str(profile.authorization_url) else "?"
    authorization_url = (
        f"{profile.authorization_url}{separator}{urlencode(parameters)}"
    )
    if not open_browser(authorization_url):
        server.server_close()
        raise RuntimeError(f"open this URL in a browser to authenticate: {authorization_url}")
    deadline = time.monotonic() + timeout_seconds
    try:
        while server.result is None and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()
    result = server.result
    if result is None:
        raise TimeoutError("OAuth login timed out before the callback was received")
    if result.get("error"):
        raise RuntimeError(f"OAuth authorization failed: {result['error']}")
    if result.get("state") != state:
        raise RuntimeError("OAuth callback state did not match")
    code = result.get("code")
    if not code:
        raise RuntimeError("OAuth callback did not contain an authorization code")
    token = token_transport(
        str(profile.token_url),
        {
            "grant_type": "authorization_code",
            "client_id": str(profile.client_id),
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
        30.0,
    )
    normalized = _normalize_token(token)
    secret_store.set(profile.name, normalized)
    return _public_token_status(normalized)


def access_token(
    profile: LLMProfile,
    *,
    store: SecretStore | None = None,
    transport: TokenTransport | None = None,
) -> str:
    if profile.auth_mode != "oauth":
        raise ValueError("access_token is only valid for OAuth profiles")
    secret_store = store or KeyringSecretStore()
    token = secret_store.get(profile.name)
    if token is None:
        raise RuntimeError(f"OAuth profile {profile.name!r} is not logged in")
    if float(token.get("expires_at", 0)) <= time.time() + 60:
        refresh_token = token.get("refresh_token")
        if not refresh_token:
            raise RuntimeError(
                f"OAuth profile {profile.name!r} expired and has no refresh token"
            )
        refreshed = (transport or _post_form)(
            str(profile.token_url),
            {
                "grant_type": "refresh_token",
                "client_id": str(profile.client_id),
                "refresh_token": str(refresh_token),
            },
            30.0,
        )
        if "refresh_token" not in refreshed:
            refreshed["refresh_token"] = refresh_token
        token = _normalize_token(refreshed)
        secret_store.set(profile.name, token)
    value = token.get("access_token")
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"OAuth profile {profile.name!r} has no access token")
    return value


def oauth_status(
    profile: LLMProfile, store: SecretStore | None = None
) -> dict[str, Any]:
    token = (store or KeyringSecretStore()).get(profile.name)
    if token is None:
        return {"logged_in": False, "expires_at": None, "refreshable": False}
    return {
        "logged_in": bool(token.get("access_token")),
        "expires_at": token.get("expires_at"),
        "refreshable": bool(token.get("refresh_token")),
    }


def oauth_logout(profile: LLMProfile, store: SecretStore | None = None) -> bool:
    return (store or KeyringSecretStore()).delete(profile.name)


class _CallbackServer(HTTPServer):
    result: dict[str, str] | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        values = parse_qs(parsed.query)
        self.server.result = {  # type: ignore[attr-defined]
            key: items[0] for key, items in values.items() if items
        }
        body = (
            b"Relic Auditor authentication received. You may close this window."
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _post_form(url: str, values: dict[str, str], timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        data=urlencode(values).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not isinstance(body, dict):
        raise RuntimeError("OAuth token endpoint returned a non-object response")
    if body.get("error"):
        raise RuntimeError(f"OAuth token exchange failed: {body['error']}")
    return body


def _normalize_token(value: dict[str, Any]) -> dict[str, Any]:
    access = value.get("access_token")
    if not isinstance(access, str) or not access:
        raise RuntimeError("OAuth token response did not contain an access token")
    expires_in = value.get("expires_in", 3600)
    try:
        expires_at = time.time() + max(0, float(expires_in))
    except (TypeError, ValueError):
        expires_at = time.time() + 3600
    return {
        "access_token": access,
        "refresh_token": value.get("refresh_token"),
        "token_type": value.get("token_type", "Bearer"),
        "scope": value.get("scope"),
        "expires_at": expires_at,
    }


def _public_token_status(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "logged_in": True,
        "expires_at": value["expires_at"],
        "refreshable": bool(value.get("refresh_token")),
    }
