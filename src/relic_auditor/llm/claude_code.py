"""Claude Code subscription provider.

Runs the locally installed Claude Code CLI in non-interactive print mode so
Relic Auditor can reuse the user's existing Claude.ai subscription session.

Hard boundaries enforced here:

- Claude credential files are never read; OAuth tokens are never extracted,
  copied, printed, exported, or stored by Relic.
- The Anthropic Messages API is never called directly by this provider.
- API-billing environment variables are removed from the child process only;
  the parent environment is never modified.
- Claude Code receives no tools, no MCP servers, no session persistence, and
  runs from an empty temporary working directory outside the scanned target.
- Every invocation is an argument list without ``shell=True``; the prompt is
  passed through stdin.
- If subscription authentication cannot be confirmed, the provider fails
  closed and deterministic reports remain intact upstream.

Subscription usage is not unlimited: reasoning consumes whatever allowance
Anthropic currently assigns to Claude Code usage on the signed-in plan, and
plan limits or account settings may still apply charges or throttling.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from ..safety import redact_secrets
from .schemas import LLMProfile


CLAUDE_EXECUTABLE = "claude"

#: API-billing variables removed from the child process so an exported API key
#: can never silently override subscription mode. The parent environment is
#: left untouched. The Bedrock/Vertex/gateway entries matter just as much as
#: the API key: they redirect Claude Code to a metered third-party account,
#: which is exactly the billing path this provider must not take.
API_BILLING_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_API_URL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_BEDROCK_BASE_URL",
    "ANTHROPIC_VERTEX_BASE_URL",
    "ANTHROPIC_VERTEX_PROJECT_ID",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_SKIP_BEDROCK_AUTH",
    "CLAUDE_CODE_SKIP_VERTEX_AUTH",
    "AWS_BEARER_TOKEN_BEDROCK",
)

DEFAULT_EFFORT = "medium"
SUPPORTED_EFFORTS = ("low", "medium", "high")
MODEL_ALIASES = ("sonnet", "opus", "haiku")

MAX_PROMPT_CHARS = 200_000
MAX_STDOUT_CHARS = 400_000
MAX_STATUS_STDOUT_CHARS = 65_536
AUTH_STATUS_TIMEOUT_SECONDS = 30.0
VERSION_TIMEOUT_SECONDS = 15.0

#: Structured output required from every Claude Code reasoning invocation.
RELIC_REASONING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "executive_summary",
        "reusable_capabilities",
        "missing_capabilities",
        "contradictions",
        "recommended_build_path",
        "risk_notes",
        "evidence_citations",
        "confidence_notes",
    ],
    "properties": {
        "executive_summary": {"type": "string"},
        "reusable_capabilities": {"type": "array", "items": {"type": "string"}},
        "missing_capabilities": {"type": "array", "items": {"type": "string"}},
        "contradictions": {"type": "array", "items": {"type": "string"}},
        "recommended_build_path": {"type": "array", "items": {"type": "string"}},
        "risk_notes": {"type": "array", "items": {"type": "string"}},
        "evidence_citations": {"type": "array", "items": {"type": "string"}},
        "confidence_notes": {"type": "string"},
    },
}

REQUIRED_ANALYSIS_KEYS = tuple(RELIC_REASONING_SCHEMA["required"])
_LIST_ANALYSIS_KEYS = tuple(
    key
    for key in REQUIRED_ANALYSIS_KEYS
    if RELIC_REASONING_SCHEMA["properties"][key]["type"] == "array"
)
MAX_ANALYSIS_ITEMS_PER_LIST = 100
MAX_ANALYSIS_ITEM_CHARS = 2_000

#: Only these keys may appear in safe status output. Emails, organization or
#: account identifiers, tokens, and credential paths are never included.
SAFE_STATUS_KEYS = (
    "ready",
    "executable_found",
    "claude_code_version",
    "logged_in",
    "authentication_type",
    "subscription_detected",
    "model",
    "effort",
    "billing_guard",
)

BILLING_GUARD_DESCRIPTION = (
    "subscription-only: API-billing environment variables are removed from the "
    "Claude Code child process; usage remains subject to Anthropic plan limits"
)


class ClaudeCodeError(RuntimeError):
    """Sanitized provider failure. Messages never contain credentials,

    account identifiers, tokens, or credential file paths."""


@dataclass(frozen=True)
class CompletedInvocation:
    """Result of one non-interactive Claude Code subprocess call."""

    returncode: int
    stdout: str
    stderr: str


SubprocessRunner = Callable[..., CompletedInvocation]
InteractiveRunner = Callable[[Sequence[str], Mapping[str, str]], int]


def _default_runner(
    args: Sequence[str],
    *,
    input_text: str = "",
    timeout: float,
    env: Mapping[str, str],
    cwd: str | None = None,
) -> CompletedInvocation:
    """Run Claude Code captured and non-interactively. Never uses a shell."""

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    completed = subprocess.run(  # noqa: S603 - fixed argument list, shell=False
        list(args),
        input=input_text,
        capture_output=True,
        timeout=timeout,
        env=dict(env),
        cwd=cwd,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    return CompletedInvocation(
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def _default_interactive_runner(
    args: Sequence[str], env: Mapping[str, str]
) -> int:
    """Run Claude Code attached to the user's terminal (login flow)."""

    completed = subprocess.run(  # noqa: S603 - fixed argument list, shell=False
        list(args),
        env=dict(env),
    )
    return completed.returncode


def _isolated_workdir():
    """A fresh empty directory for the child process.

    Every Claude Code invocation runs here rather than in Relic's own working
    directory, so the child can never resolve project files, settings, or the
    scanned estate through its cwd. Cleanup errors are ignored so a locked
    file on Windows cannot mask the real provider error.
    """

    return tempfile.TemporaryDirectory(
        prefix="relic-claude-", ignore_cleanup_errors=True
    )


def find_claude_executable() -> str | None:
    """Locate the Claude Code CLI with :func:`shutil.which` only."""

    return shutil.which(CLAUDE_EXECUTABLE)


def child_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copy the environment and strip API-billing variables for the child.

    The parent process environment is never modified.
    """

    environment = dict(base if base is not None else os.environ)
    for name in API_BILLING_ENV_VARS:
        environment.pop(name, None)
    return environment


@dataclass(frozen=True)
class AuthCheck:
    """Classified, non-sensitive view of ``claude auth status``."""

    logged_in: bool
    authentication_type: str
    subscription_detected: bool


def check_authentication(
    *,
    executable: str,
    runner: SubprocessRunner | None = None,
    timeout_seconds: float = AUTH_STATUS_TIMEOUT_SECONDS,
) -> AuthCheck:
    """Run ``claude auth status`` and classify the session without exposing

    emails, organization identifiers, tokens, or credential paths."""

    run = runner or _default_runner
    try:
        with _isolated_workdir() as workdir:
            completed = run(
                [executable, "auth", "status"],
                input_text="",
                timeout=timeout_seconds,
                env=child_environment(),
                cwd=workdir,
            )
    except subprocess.TimeoutExpired as exc:
        raise ClaudeCodeError(
            "Claude Code authentication check timed out"
        ) from exc
    except FileNotFoundError as exc:
        raise ClaudeCodeError(
            "Claude Code executable could not be started"
        ) from exc
    if completed.returncode != 0:
        return AuthCheck(
            logged_in=False,
            authentication_type="unknown",
            subscription_detected=False,
        )
    stdout = completed.stdout[:MAX_STATUS_STDOUT_CHARS]
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError:
        return AuthCheck(
            logged_in=False,
            authentication_type="unknown",
            subscription_detected=False,
        )
    if not isinstance(value, dict):
        return AuthCheck(
            logged_in=False,
            authentication_type="unknown",
            subscription_detected=False,
        )
    return _classify_auth(value)


def _strict_bool(value: Any) -> bool:
    """Interpret a JSON value as a boolean without treating the strings

    ``"false"``/``"no"``/``"0"`` as true, which plain ``bool()`` would."""

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _classify_auth(value: dict[str, Any]) -> AuthCheck:
    logged_in = _strict_bool(
        value.get("loggedIn") if "loggedIn" in value else value.get("logged_in")
    )
    method_text = " ".join(
        str(value.get(field, ""))
        for field in (
            "authMethod",
            "auth_method",
            "authType",
            "auth_type",
            "method",
            "loginMethod",
            "login_method",
            "source",
            "type",
        )
    ).lower()
    is_api_key = any(
        marker in method_text for marker in ("api key", "api-key", "apikey", "console")
    )
    # A reported API-key source means Claude Code would bill through the API
    # rather than the subscription, even when the login itself is Claude.ai.
    # Relic strips those variables from the child environment, so a healthy
    # subscription run never reports this; if it does, fail closed.
    if str(value.get("apiKeySource") or value.get("api_key_source") or "").strip():
        is_api_key = True
    is_oauth = any(
        marker in method_text
        for marker in ("oauth", "claude.ai", "claudeai", "subscription")
    )
    # API-billing evidence WINS over an OAuth-looking method string. Both
    # markers can appear at once (a Claude.ai login shadowed by an API key);
    # treating that as a subscription would defeat the billing boundary.
    if is_api_key:
        return AuthCheck(
            logged_in=logged_in,
            authentication_type="api-key",
            subscription_detected=False,
        )
    if not is_oauth:
        return AuthCheck(
            logged_in=logged_in,
            authentication_type="unknown",
            subscription_detected=False,
        )
    subscription_detected = _entitlement_active(value, logged_in)
    return AuthCheck(
        logged_in=logged_in,
        authentication_type="claude-subscription",
        subscription_detected=subscription_detected,
    )


#: Plan values Claude Code reports for an entitlement that can actually serve
#: requests. An allow-list is used deliberately: an unknown or lapsed plan must
#: fail closed rather than be assumed active.
ACTIVE_SUBSCRIPTION_VALUES = frozenset(
    {"max", "pro", "team", "enterprise", "business", "claude_max", "claude_pro"}
)

_SUBSCRIPTION_FIELDS = (
    "subscriptionType",
    "subscription_type",
    "subscription",
    "planType",
    "plan_type",
    "plan",
)


def _entitlement_active(value: dict[str, Any], logged_in: bool) -> bool:
    """Decide whether Claude reported an active subscription entitlement.

    A field that is absent, or present but null, counts as "not reported":
    Claude Code emits ``subscriptionType: null`` when an API key would take
    precedence. When nothing is reported we fall back to the login state
    rather than inventing an entitlement.
    """

    for field in _SUBSCRIPTION_FIELDS:
        reported = value.get(field)
        if reported is None:
            continue
        if isinstance(reported, bool):
            return reported
        if isinstance(reported, dict):
            # Object-shaped plans must say so explicitly.
            nested = reported.get("type") or reported.get("name") or ""
            active_flag = reported.get("active")
            if isinstance(active_flag, bool) and not active_flag:
                return False
            return str(nested).strip().lower() in ACTIVE_SUBSCRIPTION_VALUES
        text = str(reported).strip().lower()
        if not text:
            continue
        return text in ACTIVE_SUBSCRIPTION_VALUES
    # Not reported by this Claude Code build; rely on the verified login.
    return logged_in


def require_subscription(
    *,
    executable: str,
    runner: SubprocessRunner | None = None,
) -> AuthCheck:
    """Fail closed unless a logged-in Claude.ai subscription session exists."""

    check = check_authentication(executable=executable, runner=runner)
    if not check.logged_in:
        raise ClaudeCodeError(
            "Claude Code is not logged in; run 'claude auth login' and retry. "
            "Deterministic reports are unaffected."
        )
    if check.authentication_type == "api-key":
        raise ClaudeCodeError(
            "Claude Code is authenticated with a Console/API key, not a "
            "Claude.ai subscription session. This profile is subscription-only; "
            "run 'claude auth logout' then 'claude auth login' with your "
            "Claude.ai account."
        )
    if check.authentication_type != "claude-subscription":
        raise ClaudeCodeError(
            "Claude Code did not report a recognizable Claude.ai subscription "
            "session; refusing to proceed in subscription-only mode."
        )
    if not check.subscription_detected:
        raise ClaudeCodeError(
            "Claude Code did not report an active subscription entitlement; "
            "refusing to proceed in subscription-only mode."
        )
    return check


def claude_code_version(
    *,
    executable: str,
    runner: SubprocessRunner | None = None,
) -> str | None:
    run = runner or _default_runner
    try:
        with _isolated_workdir() as workdir:
            completed = run(
                [executable, "--version"],
                input_text="",
                timeout=VERSION_TIMEOUT_SECONDS,
                env=child_environment(),
                cwd=workdir,
            )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if completed.returncode != 0:
        return None
    line = completed.stdout.strip().splitlines()
    return redact_secrets(line[0].strip())[:120] if line else None


def safe_status(
    profile: LLMProfile,
    *,
    runner: SubprocessRunner | None = None,
) -> dict[str, Any]:
    """Report provider readiness using only the safe, whitelisted fields."""

    executable = find_claude_executable()
    status: dict[str, Any] = {
        "executable_found": executable is not None,
        "claude_code_version": None,
        "logged_in": False,
        "authentication_type": "unknown",
        "subscription_detected": False,
        "model": profile.model,
        "effort": profile.effort or DEFAULT_EFFORT,
        "billing_guard": BILLING_GUARD_DESCRIPTION,
    }
    if executable is not None:
        status["claude_code_version"] = claude_code_version(
            executable=executable, runner=runner
        )
        try:
            check = check_authentication(executable=executable, runner=runner)
        except ClaudeCodeError:
            check = AuthCheck(False, "unknown", False)
        status["logged_in"] = check.logged_in
        status["authentication_type"] = check.authentication_type
        status["subscription_detected"] = check.subscription_detected
    status["ready"] = bool(
        status["executable_found"]
        and status["logged_in"]
        and status["authentication_type"] == "claude-subscription"
        and status["subscription_detected"]
    )
    return {key: status[key] for key in SAFE_STATUS_KEYS}


def login(
    *,
    interactive_runner: InteractiveRunner | None = None,
) -> int:
    """Launch the official ``claude auth login`` flow attached to the user's

    terminal/browser. Relic never intercepts or parses the OAuth token."""

    executable = find_claude_executable()
    if executable is None:
        raise ClaudeCodeError(
            "Claude Code executable was not found on PATH; install Claude Code "
            "from https://claude.com/claude-code and retry."
        )
    run = interactive_runner or _default_interactive_runner
    return run([executable, "auth", "login"], child_environment())


def complete_text(
    profile: LLMProfile,
    prompt: str,
    *,
    timeout_seconds: float,
    runner: SubprocessRunner | None = None,
) -> str:
    """Invoke Claude Code print mode and return the unwrapped result text.

    The prompt travels through stdin. Claude Code receives no tools, no MCP
    configuration, no session persistence, and an empty temporary working
    directory outside the scanned target.
    """

    if len(prompt) > MAX_PROMPT_CHARS:
        raise ClaudeCodeError(
            f"reasoning prompt exceeds the bounded input size "
            f"({MAX_PROMPT_CHARS:,} characters)"
        )
    executable = find_claude_executable()
    if executable is None:
        raise ClaudeCodeError(
            "Claude Code executable was not found on PATH; install Claude Code "
            "and run 'claude auth login', or use an API-key profile instead."
        )
    require_subscription(executable=executable, runner=runner)
    args = [
        executable,
        "-p",
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(RELIC_REASONING_SCHEMA, separators=(",", ":"), sort_keys=True),
        "--model",
        profile.model,
        "--effort",
        profile.effort or DEFAULT_EFFORT,
        "--max-turns",
        "1",
        "--no-session-persistence",
        "--safe-mode",
        "--tools",
        "",
        "--strict-mcp-config",
    ]
    _assert_hardened(args)
    run = runner or _default_runner
    with _isolated_workdir() as workdir:
        try:
            completed = run(
                args,
                input_text=prompt,
                timeout=timeout_seconds,
                env=child_environment(),
                cwd=workdir,
            )
        except subprocess.TimeoutExpired as exc:
            raise ClaudeCodeError(
                f"Claude Code timed out after {timeout_seconds:g} seconds"
            ) from exc
        except FileNotFoundError as exc:
            raise ClaudeCodeError(
                "Claude Code executable could not be started"
            ) from exc
    if completed.returncode != 0:
        # Claude Code stderr can carry account identifiers, paths, and other
        # environment detail. It is summarized, never forwarded: only the
        # exit status and a coarse classification reach reports and the CLI.
        raise ClaudeCodeError(
            f"Claude Code exited with status {completed.returncode} "
            f"({_stderr_category(completed.stderr)})"
        )
    stdout = completed.stdout
    if len(stdout) > MAX_STDOUT_CHARS:
        raise ClaudeCodeError(
            f"Claude Code returned oversized output "
            f"(more than {MAX_STDOUT_CHARS:,} characters)"
        )
    if not stdout.strip():
        raise ClaudeCodeError("Claude Code returned no output")
    return _unwrap_result(stdout)


#: Flags that must be present on every reasoning invocation. Checked at call
#: time so an edit that drops one fails loudly instead of silently handing
#: Claude Code tools, MCP access, or a multi-turn session.
REQUIRED_INVOCATION_FLAGS = (
    "-p",
    "--output-format",
    "--json-schema",
    "--max-turns",
    "--no-session-persistence",
    "--safe-mode",
    "--tools",
    "--strict-mcp-config",
)
FORBIDDEN_INVOCATION_FLAGS = ("--dangerously-skip-permissions",)


def _assert_hardened(args: Sequence[str]) -> None:
    missing = [flag for flag in REQUIRED_INVOCATION_FLAGS if flag not in args]
    if missing:
        raise ClaudeCodeError(
            "refusing to invoke Claude Code without its hardening flags: "
            + ", ".join(missing)
        )
    present = [flag for flag in FORBIDDEN_INVOCATION_FLAGS if flag in args]
    if present:
        raise ClaudeCodeError(
            "refusing to invoke Claude Code with unsafe flags: "
            + ", ".join(present)
        )
    tools_index = list(args).index("--tools")
    if tools_index + 1 >= len(args) or args[tools_index + 1] != "":
        raise ClaudeCodeError(
            "refusing to invoke Claude Code with a non-empty tool set"
        )


#: Coarse, non-sensitive classifications for a failed invocation. Raw stderr is
#: never surfaced; only which bucket it fell into.
_STDERR_CATEGORIES = (
    ("authentication", ("auth", "login", "unauthor", "credential", "forbidden")),
    ("rate limit or quota", ("rate limit", "quota", "429", "usage limit", "overloaded")),
    ("network", ("network", "connect", "timeout", "dns", "socket", "proxy")),
    ("invalid request", ("invalid", "unknown option", "unrecognized", "usage:")),
)


def _stderr_category(stderr: str) -> str:
    text = (stderr or "").lower()
    if not text.strip():
        return "no diagnostic output"
    for label, markers in _STDERR_CATEGORIES:
        if any(marker in text for marker in markers):
            return f"{label} error reported by Claude Code"
    return "see Claude Code output; details withheld to avoid leaking account data"


def _unwrap_result(stdout: str) -> str:
    """Extract the result payload from Claude Code's JSON envelope."""

    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ClaudeCodeError("Claude Code returned invalid JSON") from exc
    if isinstance(envelope, dict):
        if envelope.get("is_error") is True or envelope.get("subtype") not in (
            None,
            "success",
        ):
            raise ClaudeCodeError("Claude Code reported an unsuccessful result")
        for key in ("structured_output", "result", "content", "output"):
            if key in envelope:
                payload = envelope[key]
                if isinstance(payload, str):
                    return payload
                return json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return json.dumps(envelope, sort_keys=True, ensure_ascii=False)
    raise ClaudeCodeError("Claude Code returned an unexpected response shape")


def validate_analysis(
    analysis: dict[str, Any],
    evidence_text: str,
    anchors: Sequence[str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Validate the structured result before it is used.

    Raises :class:`ClaudeCodeError` when required structure is missing so the
    caller records a sanitized provider error and keeps deterministic reports.
    Evidence citations that do not appear in the deterministic evidence
    envelope are dropped with a warning; the model cannot introduce evidence.
    """

    if not isinstance(analysis, dict) or "unstructured_response" in analysis:
        raise ClaudeCodeError(
            "Claude Code output was not the required structured JSON object"
        )
    missing = [key for key in REQUIRED_ANALYSIS_KEYS if key not in analysis]
    if missing:
        raise ClaudeCodeError(
            "Claude Code structured output is incomplete; missing: "
            + ", ".join(sorted(missing))
        )
    summary = analysis.get("executive_summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ClaudeCodeError(
            "Claude Code structured output has an empty executive_summary"
        )
    confidence = analysis.get("confidence_notes")
    if not isinstance(confidence, str):
        raise ClaudeCodeError(
            "Claude Code structured output has invalid confidence_notes"
        )
    warnings: list[str] = []
    validated: dict[str, Any] = {
        "executive_summary": summary[:MAX_ANALYSIS_ITEM_CHARS],
        "confidence_notes": confidence[:MAX_ANALYSIS_ITEM_CHARS],
    }
    for key in _LIST_ANALYSIS_KEYS:
        value = analysis.get(key)
        if not isinstance(value, list):
            raise ClaudeCodeError(
                f"Claude Code structured output field is not a list: {key}"
            )
        items = [
            str(item)[:MAX_ANALYSIS_ITEM_CHARS]
            for item in value[:MAX_ANALYSIS_ITEMS_PER_LIST]
            if str(item).strip()
        ]
        if len(value) > MAX_ANALYSIS_ITEMS_PER_LIST:
            warnings.append(
                f"Structured output list '{key}' was truncated to "
                f"{MAX_ANALYSIS_ITEMS_PER_LIST} items."
            )
        validated[key] = items
    cited = validated["evidence_citations"]
    corpus = _citation_corpus(evidence_text)
    anchor_set = _usable_anchors(anchors)
    supported = [
        item for item in cited if _citation_supported(item, corpus, anchor_set)
    ]
    dropped = len(cited) - len(supported)
    if dropped:
        warnings.append(
            f"Dropped {dropped} evidence citation(s) that do not appear in the "
            "deterministic evidence envelope; the model cannot introduce "
            "evidence."
        )
    validated["evidence_citations"] = supported
    return validated, warnings


#: A citation shorter than this carries no information and would match almost
#: any corpus by chance, so it cannot be used to claim evidence.
MIN_CITATION_CHARS = 4


def _citation_corpus(evidence_text: str) -> str:
    """Normalize the evidence envelope for containment checks.

    The envelope is JSON, so string values arrive escaped (``\\"``, ``\\n``,
    ``\\\\``). Comparing a decoded model citation against escaped text would
    reject legitimate verbatim quotes, so both sides are normalized to
    lowercase text with collapsed whitespace and JSON escapes undone.
    """

    text = (
        evidence_text.replace("\\n", " ")
        .replace("\\t", " ")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
        .replace("\\/", "/")
    )
    return _normalize_citation(text)


def _normalize_citation(value: str) -> str:
    return " ".join(value.lower().split())


#: Minimum length for an evidence anchor (a path or capability name pulled
#: from the deterministic inventory) to license a citation.
MIN_ANCHOR_CHARS = 6

#: Generic vocabulary that appears throughout the envelope and would license
#: almost any citation, so it never counts as an anchor.
_ANCHOR_STOPWORDS = frozenset(
    {
        "source",
        "sources",
        "filesystem",
        "medium",
        "high",
        "low",
        "true",
        "false",
        "python",
        "unknown",
        "candidate",
        "candidates",
        "evidence",
        "schema_version",
    }
)


def _usable_anchors(anchors: Sequence[str] | None) -> tuple[str, ...]:
    if not anchors:
        return ()
    seen: list[str] = []
    for anchor in anchors:
        normalized = _normalize_citation(str(anchor))
        if len(normalized) < MIN_ANCHOR_CHARS:
            continue
        if normalized in _ANCHOR_STOPWORDS:
            continue
        if normalized not in seen:
            seen.append(normalized)
    return tuple(seen)


def _citation_supported(
    citation: str, corpus: str, anchors: Sequence[str] = ()
) -> bool:
    """Decide whether a citation is grounded in the deterministic evidence.

    Two ways to qualify:

    1. the citation appears verbatim in the evidence envelope, or
    2. it names a concrete anchor from the deterministic inventory (a file
       path or capability name), which lets the model write natural
       references like ``gov.py:1`` or ``gov.py (approval_queue)`` without
       being able to invent a file or capability that was never observed.

    Anything shorter than :data:`MIN_CITATION_CHARS`, or naming nothing the
    scanner actually recorded, is dropped.
    """

    normalized = _normalize_citation(citation)
    if len(normalized) < MIN_CITATION_CHARS:
        return False
    if normalized in corpus:
        return True
    return any(anchor in normalized for anchor in anchors)
