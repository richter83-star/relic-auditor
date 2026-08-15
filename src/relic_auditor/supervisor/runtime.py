from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from .schemas import ActionOperation, ActionProposal, SupervisorError


class ExecutionBoundary(str, Enum):
    """Declared containment boundary for a process action."""

    DIRECT = "direct"
    PROVIDER_SANDBOX = "provider_sandbox"
    RESTRICTED_PROVIDER = "restricted_provider"
    WINDOWS_SANDBOX = "windows_sandbox"
    UNISOLATED = "unisolated"


@dataclass(frozen=True)
class IsolationAssessment:
    boundary: ExecutionBoundary
    provider: str
    enforced: bool
    production_supported: bool
    reason: str

    def public(self) -> dict[str, object]:
        return {
            "boundary": self.boundary.value,
            "provider": self.provider,
            "enforced": self.enforced,
            "production_supported": self.production_supported,
            "reason": self.reason,
        }


_CLAUDE_REQUIRED_ARGUMENTS = {
    "-p",
    "--no-session-persistence",
    "--safe-mode",
    "--strict-mcp-config",
}


def _argv(action: ActionProposal) -> tuple[str, ...]:
    value = action.parameters.get("argv", [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return ()
    return tuple(value)


def _is_exact_codex_profile(argv: tuple[str, ...]) -> bool:
    """Accept only the profile emitted by ``codex_builder_action``."""

    if not argv or Path(argv[0]).name.casefold() not in {"codex", "codex.exe"}:
        return False
    expected = [
        "exec",
        "--ephemeral",
        "--sandbox",
        "workspace-write",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
    ]
    tail = list(argv[1:])
    if tail[: len(expected)] != expected:
        return False
    tail = tail[len(expected) :]
    if len(tail) == 1:
        return tail == ["-"]
    if len(tail) == 3 and tail[0] == "--model":
        model = tail[1].strip()
        return bool(model) and not model.startswith("-") and tail[2] == "-"
    return False


def assess_action_isolation(
    action: ActionProposal,
    *,
    platform_name: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> IsolationAssessment:
    """Verify a claimed boundary against an exact, known-safe process profile."""

    if action.operation == ActionOperation.WRITE_TEXT:
        return IsolationAssessment(
            ExecutionBoundary.DIRECT,
            "relic",
            True,
            True,
            "Relic performs the path-confined write directly.",
        )
    raw_boundary = str(
        action.parameters.get("execution_boundary", ExecutionBoundary.UNISOLATED.value)
    )
    try:
        boundary = ExecutionBoundary(raw_boundary)
    except ValueError:
        return IsolationAssessment(
            ExecutionBoundary.UNISOLATED,
            str(action.parameters.get("provider", "unknown")),
            False,
            False,
            "The action declares an unknown execution boundary.",
        )
    provider = str(action.parameters.get("provider", "native-process"))
    argv = _argv(action)
    executable = Path(argv[0]).name.casefold() if argv else ""

    if boundary == ExecutionBoundary.PROVIDER_SANDBOX:
        valid = bool(
            provider == "codex-cli"
            and _is_exact_codex_profile(argv)
            and action.parameters.get("provider_sandbox") == "workspace-write"
        )
        return IsolationAssessment(
            boundary,
            provider,
            valid,
            valid,
            (
                "Exact Codex ephemeral workspace-write profile verified."
                if valid
                else "The claimed Codex sandbox profile is incomplete or altered."
            ),
        )

    if boundary == ExecutionBoundary.RESTRICTED_PROVIDER:
        valid = bool(
            provider == "claude-code-cli"
            and executable in {"claude", "claude.exe", "claude.cmd"}
            and _CLAUDE_REQUIRED_ARGUMENTS <= set(argv[1:])
            and "Bash" not in str(action.parameters.get("provider_tools", []))
        )
        return IsolationAssessment(
            boundary,
            provider,
            valid,
            False,
            (
                "Claude file-tool restrictions were recognized, but they are not an "
                "OS isolation boundary and commercial subscription integration is not approved."
                if valid
                else "The claimed restricted-provider profile is incomplete or altered."
            ),
        )

    if boundary == ExecutionBoundary.WINDOWS_SANDBOX:
        available = bool(
            (platform_name or os.name) in {"nt", "win32"}
            and which("WindowsSandbox.exe")
        )
        return IsolationAssessment(
            boundary,
            provider,
            available,
            False,
            (
                "Windows Sandbox is installed, but the v0.12 host/guest runner is not enabled."
                if available
                else "Windows Sandbox is unavailable on this system."
            ),
        )

    return IsolationAssessment(
        boundary,
        provider,
        False,
        False,
        "A native process has the current user's operating-system authority.",
    )


@dataclass(frozen=True)
class ExecutionPolicy:
    """Fail-closed policy applied before every supervised process starts."""

    allowed_boundaries: frozenset[ExecutionBoundary]
    policy_name: str = "production-fail-closed"

    @classmethod
    def production(cls) -> "ExecutionPolicy":
        return cls(
            frozenset({ExecutionBoundary.DIRECT, ExecutionBoundary.PROVIDER_SANDBOX})
        )

    @classmethod
    def testing(cls) -> "ExecutionPolicy":
        # Code-level injected runners only; this is not exposed through the
        # desktop, CLI, configuration, or environment.
        return cls(frozenset(ExecutionBoundary), "injected-test-runner")

    def require(self, action: ActionProposal) -> IsolationAssessment:
        assessment = assess_action_isolation(action)
        if assessment.boundary not in self.allowed_boundaries:
            raise SupervisorError("production execution refused: " + assessment.reason)
        if (
            self.policy_name == "production-fail-closed"
            and not assessment.production_supported
        ):
            raise SupervisorError("production execution refused: " + assessment.reason)
        return assessment
