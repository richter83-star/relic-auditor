from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..build_packs.canonical import digest


SUPERVISOR_SCHEMA = "1.0"


class SupervisorError(RuntimeError):
    """Base error for fail-closed supervised-build operations."""


class SessionState(str, Enum):
    CREATED = "created"
    PLANNED = "planned"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    CANCELLING = "cancelling"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    FAILED = "failed"
    CANDIDATE_READY = "candidate_ready"


class Capability(str, Enum):
    FILE_WRITE = "file_write"
    PROCESS = "process"
    DEPENDENCY_INSTALL = "dependency_install"
    NETWORK = "network"
    CREDENTIALS = "credentials"
    GIT = "git"
    EXTERNAL_ACTION = "external_action"


class ActionOperation(str, Enum):
    WRITE_TEXT = "write_text"
    RUN_PROCESS = "run_process"
    INSTALL_DEPENDENCIES = "install_dependencies"
    GIT_COMMAND = "git_command"
    EXTERNAL_ACTION = "external_action"


_REQUIRED_CAPABILITIES = {
    ActionOperation.WRITE_TEXT: frozenset({Capability.FILE_WRITE}),
    ActionOperation.RUN_PROCESS: frozenset({Capability.PROCESS}),
    ActionOperation.INSTALL_DEPENDENCIES: frozenset(
        {Capability.PROCESS, Capability.DEPENDENCY_INSTALL, Capability.NETWORK}
    ),
    ActionOperation.GIT_COMMAND: frozenset({Capability.PROCESS, Capability.GIT}),
    ActionOperation.EXTERNAL_ACTION: frozenset(
        {Capability.PROCESS, Capability.NETWORK, Capability.EXTERNAL_ACTION}
    ),
}


@dataclass(frozen=True)
class ActionProposal:
    action_id: str
    operation: ActionOperation
    summary: str
    capabilities: tuple[Capability, ...]
    parameters: Mapping[str, Any]
    risk: str = "review"

    @classmethod
    def create(
        cls,
        operation: ActionOperation | str,
        summary: str,
        capabilities: Sequence[Capability | str],
        parameters: Mapping[str, Any],
        *,
        risk: str = "review",
    ) -> "ActionProposal":
        op = ActionOperation(operation)
        caps = tuple(sorted({Capability(item) for item in capabilities}, key=lambda x: x.value))
        normalized = {
            "operation": op.value,
            "summary": str(summary).strip(),
            "capabilities": [item.value for item in caps],
            "parameters": dict(parameters),
            "risk": str(risk),
        }
        proposal = cls(
            action_id=f"action_{digest(normalized)[:24]}",
            operation=op,
            summary=normalized["summary"],
            capabilities=caps,
            parameters=normalized["parameters"],
            risk=normalized["risk"],
        )
        proposal.validate()
        return proposal

    def validate(self) -> None:
        if not self.summary or len(self.summary) > 500:
            raise SupervisorError("action summary must contain 1 to 500 characters")
        if self.risk not in {"low", "review", "high"}:
            raise SupervisorError("action risk must be low, review, or high")
        required = _REQUIRED_CAPABILITIES[self.operation]
        if not required <= set(self.capabilities):
            missing = ", ".join(sorted(item.value for item in required - set(self.capabilities)))
            raise SupervisorError(f"action is missing required capabilities: {missing}")
        expected = f"action_{digest(self.content())[:24]}"
        if self.action_id != expected:
            raise SupervisorError("action proposal identity is invalid")

    def content(self) -> dict[str, Any]:
        return {
            "operation": self.operation.value,
            "summary": self.summary,
            "capabilities": [item.value for item in self.capabilities],
            "parameters": dict(self.parameters),
            "risk": self.risk,
        }

    def public(self, *, include_parameters: bool = True) -> dict[str, Any]:
        result = {"schema_version": SUPERVISOR_SCHEMA, "action_id": self.action_id, **self.content()}
        if not include_parameters:
            result["parameters"] = {"sha256": digest(dict(self.parameters))}
        return result

    @classmethod
    def from_public(cls, value: Mapping[str, Any]) -> "ActionProposal":
        proposal = cls(
            action_id=str(value["action_id"]),
            operation=ActionOperation(str(value["operation"])),
            summary=str(value["summary"]),
            capabilities=tuple(Capability(item) for item in value["capabilities"]),
            parameters=dict(value.get("parameters", {})),
            risk=str(value.get("risk", "review")),
        )
        proposal.validate()
        return proposal


@dataclass(frozen=True)
class ApprovalGrant:
    approval_id: str
    session_id: str
    action_id: str
    capabilities: tuple[Capability, ...]
    actor: str
    approved_at: str

    @classmethod
    def create(
        cls,
        session_id: str,
        action: ActionProposal,
        capabilities: Sequence[Capability | str],
        *,
        actor: str,
        approved_at: str,
    ) -> "ApprovalGrant":
        caps = tuple(sorted({Capability(item) for item in capabilities}, key=lambda x: x.value))
        content = {
            "session_id": session_id,
            "action_id": action.action_id,
            "capabilities": [item.value for item in caps],
            "actor": actor.strip(),
            "approved_at": approved_at,
        }
        if not content["actor"] or len(content["actor"]) > 200:
            raise SupervisorError("approval actor must contain 1 to 200 characters")
        return cls(f"grant_{digest(content)[:24]}", session_id, action.action_id, caps, content["actor"], approved_at)

    def public(self) -> dict[str, Any]:
        return {
            "schema_version": SUPERVISOR_SCHEMA,
            "approval_id": self.approval_id,
            "session_id": self.session_id,
            "action_id": self.action_id,
            "capabilities": [item.value for item in self.capabilities],
            "actor": self.actor,
            "approved_at": self.approved_at,
        }


@dataclass(frozen=True)
class BudgetLimits:
    max_actions: int = 100
    max_written_files: int = 1_000
    max_written_bytes: int = 100 * 1024 * 1024
    max_process_seconds: float = 1_800.0
    max_network_actions: int = 10
    max_external_actions: int = 0

    def validate(self) -> None:
        if min(
            self.max_actions,
            self.max_written_files,
            self.max_written_bytes,
            self.max_network_actions,
            self.max_external_actions,
        ) < 0 or self.max_process_seconds < 0:
            raise SupervisorError("supervisor budgets cannot be negative")

    def public(self) -> dict[str, Any]:
        self.validate()
        return {
            "max_actions": self.max_actions,
            "max_written_files": self.max_written_files,
            "max_written_bytes": self.max_written_bytes,
            "max_process_seconds": self.max_process_seconds,
            "max_network_actions": self.max_network_actions,
            "max_external_actions": self.max_external_actions,
        }


@dataclass
class BudgetUsage:
    actions: int = 0
    written_files: int = 0
    written_bytes: int = 0
    process_seconds: float = 0.0
    network_actions: int = 0
    external_actions: int = 0

    def public(self) -> dict[str, Any]:
        return {
            "actions": self.actions,
            "written_files": self.written_files,
            "written_bytes": self.written_bytes,
            "process_seconds": round(self.process_seconds, 6),
            "network_actions": self.network_actions,
            "external_actions": self.external_actions,
        }

    @classmethod
    def from_public(cls, value: Mapping[str, Any]) -> "BudgetUsage":
        return cls(**{name: value.get(name, default) for name, default in cls().public().items()})


@dataclass
class SupervisorSession:
    session_id: str
    pack_id: str
    pack_content_hash: str
    root: Path
    state: SessionState
    budgets: BudgetLimits = field(default_factory=BudgetLimits)
    usage: BudgetUsage = field(default_factory=BudgetUsage)
    queued_actions: list[str] = field(default_factory=list)
    completed_actions: list[str] = field(default_factory=list)
    failed_actions: list[str] = field(default_factory=list)
    cancelled_actions: list[str] = field(default_factory=list)
    created_at: str = ""

    @property
    def workspace(self) -> Path:
        return self.root / "workspace"

    @property
    def control(self) -> Path:
        return self.root / "control"

    @property
    def input(self) -> Path:
        return self.root / "input"

    def public(self) -> dict[str, Any]:
        return {
            "schema_version": SUPERVISOR_SCHEMA,
            "session_id": self.session_id,
            "pack_id": self.pack_id,
            "pack_content_hash": self.pack_content_hash,
            "state": self.state.value,
            "budgets": self.budgets.public(),
            "usage": self.usage.public(),
            "queued_actions": list(self.queued_actions),
            "completed_actions": list(self.completed_actions),
            "failed_actions": list(self.failed_actions),
            "cancelled_actions": list(self.cancelled_actions),
            "created_at": self.created_at,
        }
