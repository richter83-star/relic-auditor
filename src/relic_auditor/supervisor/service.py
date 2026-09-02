from __future__ import annotations

import json
import hashlib
import os
import re
import signal
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ..build_packs.canonical import (
    canonical_bytes,
    digest,
    source_root_path_fingerprint,
)
from ..build_packs.exporter import validate_export
from ..product_discovery.entitlements import (
    Entitlement,
    ProductCapability,
)
from ..safety import redact_secrets
from .adapters import BuildAdapter
from .ledger import AppendOnlyLedger
from .runtime import ExecutionPolicy, IsolationAssessment
from .schemas import (
    ActionOperation,
    ActionProposal,
    ApprovalGrant,
    BudgetLimits,
    BudgetUsage,
    Capability,
    SessionState,
    SupervisorError,
    SupervisorSession,
)
from .workspace import (
    copy_verified_tree,
    file_manifest,
    manifest_diff,
    safe_workspace_path,
)


MAX_ACTION_FILE_BYTES = 8 * 1024 * 1024
MAX_PROCESS_OUTPUT_CHARS = 200_000
MAX_ARG_COUNT = 256
MAX_ARG_CHARS = 32_768
_JSON_LOCKS_GUARD = threading.Lock()
_JSON_LOCKS: dict[Path, threading.RLock] = {}


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


ProcessRunner = Callable[..., ProcessResult]


class ProcessCancelledError(SupervisorError):
    """An operator cancelled an active supervised process."""


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json_lock_for(path: Path) -> threading.RLock:
    key = path.expanduser().resolve()
    with _JSON_LOCKS_GUARD:
        return _JSON_LOCKS.setdefault(key, threading.RLock())


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    with _json_lock_for(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_bytes(canonical_bytes(value))
        os.replace(temporary, path)


def _default_process_runner(
    argv: Sequence[str],
    *,
    cwd: str,
    input_text: str,
    timeout: float,
    env: Mapping[str, str],
    cancel_event: threading.Event,
) -> ProcessResult:
    creationflags = 0
    popen_kwargs: dict[str, Any] = {}
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        popen_kwargs["start_new_session"] = True
    with (
        tempfile.TemporaryFile() as stdin_file,
        tempfile.TemporaryFile() as stdout_file,
        tempfile.TemporaryFile() as stderr_file,
    ):
        stdin_file.write(input_text.encode("utf-8"))
        stdin_file.seek(0)
        process = subprocess.Popen(  # noqa: S603 - exact reviewed argv, never a shell
            list(argv),
            cwd=cwd,
            stdin=stdin_file,
            stdout=stdout_file,
            stderr=stderr_file,
            env=dict(env),
            shell=False,
            close_fds=True,
            creationflags=creationflags,
            **popen_kwargs,
        )
        started = time.monotonic()
        while process.poll() is None:
            if cancel_event.wait(0.05):
                _terminate_process_tree(process)
                raise ProcessCancelledError(
                    "approved process was cancelled; its process tree was terminated"
                )
            if time.monotonic() - started >= timeout:
                _terminate_process_tree(process)
                raise subprocess.TimeoutExpired(list(argv), timeout)
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read().decode("utf-8", errors="replace")
        stderr = stderr_file.read().decode("utf-8", errors="replace")
        return ProcessResult(int(process.returncode or 0), stdout, stderr)


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Terminate the whole child tree, then force-kill if it does not exit."""

    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(  # noqa: S603 - fixed Windows system command and numeric PID
            ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            process.terminate()
    try:
        process.wait(timeout=1.0)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "nt":
        process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()
    process.wait(timeout=2.0)


class SupervisorService:
    """Owns the complete approval-gated build lifecycle.

    The service never receives the original scan target. It consumes only a
    checksum-verified exported Build Pack and creates a new managed workspace.
    Process actions remain explicit, separately approved high-risk operations.
    """

    def __init__(
        self,
        entitlement: Entitlement,
        *,
        process_runner: ProcessRunner | None = None,
        execution_policy: ExecutionPolicy | None = None,
    ) -> None:
        self.entitlement = entitlement
        self._uses_default_runner = process_runner is None
        self.process_runner = process_runner or _default_process_runner
        self.execution_policy = execution_policy or (
            ExecutionPolicy.production()
            if self._uses_default_runner
            else ExecutionPolicy.testing()
        )
        self._cancel_events: dict[str, threading.Event] = {}
        self._running_actions: dict[str, str] = {}

    def create_session(
        self,
        build_pack: Path,
        sessions_root: Path,
        *,
        budgets: BudgetLimits | None = None,
    ) -> SupervisorSession:
        self.entitlement.require(ProductCapability.SUPERVISED_BUILD)
        limits = budgets or BudgetLimits()
        limits.validate()
        source = build_pack.expanduser().resolve()
        status = validate_export(source)
        destination_root = sessions_root.expanduser().resolve()
        source_root_hash = status.get("source_root_path_sha256")
        if not isinstance(source_root_hash, str):
            raise SupervisorError(
                "Build Pack predates the v0.11 source boundary; re-export it before building"
            )
        for ancestor in (destination_root, *destination_root.parents):
            if source_root_path_fingerprint(ancestor) == source_root_hash:
                raise SupervisorError(
                    "managed build sessions must remain outside the original scan target"
                )
        if destination_root == source or destination_root.is_relative_to(source):
            raise SupervisorError("managed build sessions must be outside the Build Pack")
        destination_root.mkdir(parents=True, exist_ok=True)
        session_id = f"session_{status['pack_id'][3:15]}_{uuid.uuid4().hex[:12]}"
        staging = destination_root / f".{session_id}.staging"
        final = destination_root / session_id
        staging.mkdir()
        try:
            (staging / "control" / "actions").mkdir(parents=True)
            (staging / "control" / "approvals").mkdir(parents=True)
            (staging / "control" / "logs").mkdir(parents=True)
            (staging / "checkpoints").mkdir(parents=True)
            (staging / "workspace").mkdir(parents=True)
            (staging / "input").mkdir(parents=True)
            copy_verified_tree(source, staging / "input")
            # Close the validation/copy race on both sides: the source must
            # still validate after the copy, and the private copy must be a
            # complete independently verifiable Build Pack.
            validate_export(source)
            validate_export(staging / "input")
            assets = staging / "input" / "assets"
            if assets.is_dir():
                copy_verified_tree(assets, staging / "workspace")
            relic_context = staging / "workspace" / ".relic" / "build-pack"
            relic_context.mkdir(parents=True)
            for name in (
                "build-pack.json",
                "build-pack-manifest.json",
                "BRIEF.md",
                "MVP_SCOPE.md",
                "ARCHITECTURE.md",
                "IMPLEMENTATION_PLAN.md",
                "ACCEPTANCE_CRITERIA.md",
                "PROVENANCE.md",
                "RISKS_AND_DECISIONS.md",
                "RELIC_CONTEXT.json",
            ):
                candidate = staging / "input" / name
                if candidate.is_file():
                    shutil.copy2(candidate, relic_context / name)
            session = SupervisorSession(
                session_id=session_id,
                pack_id=str(status["pack_id"]),
                pack_content_hash=str(status["content_hash"]),
                root=final,
                state=SessionState.CREATED,
                budgets=limits,
                created_at=_now(),
            )
            initial = file_manifest(staging / "workspace")
            _atomic_json(staging / "control" / "initial-manifest.json", initial)
            _atomic_json(staging / "control" / "session.json", session.public())
            staging.rename(final)
            ledger = self._ledger(session)
            ledger.append(
                "session_created",
                {
                    "session_id": session.session_id,
                    "pack_id": session.pack_id,
                    "pack_content_hash": session.pack_content_hash,
                    "workspace_manifest_hash": digest(initial),
                    "budgets": limits.public(),
                },
            )
            return session
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def load_session(self, root: Path) -> SupervisorSession:
        session_root = root.expanduser().resolve()
        path = session_root / "control" / "session.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise SupervisorError("managed build session is missing or invalid") from exc
        limits = BudgetLimits(**dict(value["budgets"]))
        limits.validate()
        session = SupervisorSession(
            session_id=str(value["session_id"]),
            pack_id=str(value["pack_id"]),
            pack_content_hash=str(value["pack_content_hash"]),
            root=session_root,
            state=SessionState(str(value["state"])),
            budgets=limits,
            usage=BudgetUsage.from_public(value.get("usage", {})),
            queued_actions=list(map(str, value.get("queued_actions", []))),
            completed_actions=list(map(str, value.get("completed_actions", []))),
            failed_actions=list(map(str, value.get("failed_actions", []))),
            cancelled_actions=list(map(str, value.get("cancelled_actions", []))),
            created_at=str(value.get("created_at", "")),
        )
        if not session.workspace.is_dir() or not session.input.is_dir():
            raise SupervisorError("managed build session directories are incomplete")
        ledger = self._ledger(session)
        ledger.verify()
        entries = ledger.entries()
        created = next(
            (item.get("details", {}) for item in entries if item.get("event") == "session_created"),
            None,
        )
        if not isinstance(created, dict) or any(
            (
                created.get("session_id") != session.session_id,
                created.get("pack_id") != session.pack_id,
                created.get("pack_content_hash") != session.pack_content_hash,
                created.get("budgets") != session.budgets.public(),
            )
        ):
            raise SupervisorError("session metadata does not match its ledger")
        queued = [
            str(item.get("details", {}).get("action_id"))
            for item in entries
            if item.get("event") == "action_queued"
        ]
        completed = [
            str(item.get("details", {}).get("action_id"))
            for item in entries
            if item.get("event") == "action_completed"
        ]
        failed = [
            str(item.get("details", {}).get("action_id"))
            for item in entries
            if item.get("event") == "action_failed"
        ]
        cancelled = [
            str(item.get("details", {}).get("action_id"))
            for item in entries
            if item.get("event") == "action_cancelled"
        ]
        if (
            queued != session.queued_actions
            or completed != session.completed_actions
            or failed != session.failed_actions
            or cancelled != session.cancelled_actions
        ):
            raise SupervisorError("session action state does not match its ledger")
        return session

    def plan(self, session: SupervisorSession, adapter: BuildAdapter) -> tuple[ActionProposal, ...]:
        self._require_active(session)
        proposals = tuple(adapter.plan(session))
        if not proposals:
            raise SupervisorError("builder adapter returned no actions")
        if len(session.queued_actions) + len(proposals) > session.budgets.max_actions:
            raise SupervisorError("action plan exceeds the session budget")
        seen = set(session.queued_actions)
        for action in proposals:
            action.validate()
            if action.action_id in seen:
                raise SupervisorError("action plan contains a duplicate action")
            encoded = canonical_bytes(action.public())
            if len(encoded) > MAX_ACTION_FILE_BYTES:
                raise SupervisorError("action proposal exceeds the size limit")
            (session.control / "actions").mkdir(parents=True, exist_ok=True)
            (session.control / "actions" / f"{action.action_id}.json").write_bytes(encoded)
            session.queued_actions.append(action.action_id)
            seen.add(action.action_id)
            self._ledger(session).append(
                "action_queued",
                {
                    "action_id": action.action_id,
                    "operation": action.operation.value,
                    "summary": action.summary,
                    "capabilities": [item.value for item in action.capabilities],
                    "parameter_hash": digest(dict(action.parameters)),
                    "adapter": adapter.name,
                },
            )
        session.state = SessionState.WAITING_APPROVAL
        self._save(session)
        return proposals

    def list_actions(self, session: SupervisorSession) -> tuple[ActionProposal, ...]:
        return tuple(self._load_action(session, action_id) for action_id in session.queued_actions)

    def approve(
        self,
        session: SupervisorSession,
        action_id: str,
        capabilities: Sequence[Capability | str],
        *,
        actor: str,
    ) -> ApprovalGrant:
        self._require_active(session)
        action = self._load_action(session, action_id)
        grant = ApprovalGrant.create(
            session.session_id,
            action,
            capabilities,
            actor=actor,
            approved_at=_now(),
        )
        if not set(grant.capabilities) <= set(action.capabilities):
            raise SupervisorError("approval includes a capability not requested by the action")
        _atomic_json(session.control / "approvals" / f"{action_id}.json", grant.public())
        self._ledger(session).append(
            "action_approved",
            {
                "action_id": action_id,
                "approval_id": grant.approval_id,
                "actor": grant.actor,
                "capabilities": [item.value for item in grant.capabilities],
            },
        )
        return grant

    def execute(self, session: SupervisorSession, action_id: str) -> dict[str, Any]:
        self.entitlement.require(ProductCapability.SUPERVISED_BUILD)
        self._require_active(session)
        if action_id in session.completed_actions:
            raise SupervisorError("action was already completed")
        action = self._load_action(session, action_id)
        approval = self._load_approval(session, action)
        missing = set(action.capabilities) - set(approval.capabilities)
        if missing:
            raise SupervisorError(
                "action is not fully approved; missing: "
                + ", ".join(sorted(item.value for item in missing))
            )
        self._check_budget_before(session, action)
        try:
            isolation = self.execution_policy.require(action)
        except SupervisorError as exc:
            self._ledger(session).append(
                "action_blocked",
                {"action_id": action.action_id, "reason": str(exc)},
            )
            raise
        checkpoint = self.create_checkpoint(session, label=f"before-{action.action_id}")
        cancel_event = threading.Event()
        if action.operation != ActionOperation.WRITE_TEXT:
            self._cancel_events[session.session_id] = cancel_event
            self._running_actions[session.session_id] = action.action_id
        session.state = SessionState.RUNNING
        self._save(session)
        self._ledger(session).append(
            "action_started",
            {
                "action_id": action.action_id,
                "checkpoint_id": checkpoint["checkpoint_id"],
                "isolation": isolation.public(),
            },
        )
        try:
            if action.operation == ActionOperation.WRITE_TEXT:
                result = self._write_text(session, action)
            else:
                result = self._run_process(
                    session, action, checkpoint, cancel_event, isolation
                )
            session.usage.actions += 1
            session.completed_actions.append(action.action_id)
            session.state = (
                SessionState.WAITING_APPROVAL
                if set(session.queued_actions)
                - set(session.completed_actions)
                - set(session.failed_actions)
                - set(session.cancelled_actions)
                else SessionState.PAUSED
            )
            self._save(session)
            self._ledger(session).append(
                "action_completed",
                {
                    "action_id": action.action_id,
                    "result": result,
                    "usage": session.usage.public(),
                },
            )
            return result
        except ProcessCancelledError:
            if action.action_id not in session.cancelled_actions:
                session.cancelled_actions.append(action.action_id)
            session.state = SessionState.CANCELLED
            self._save(session)
            self._ledger(session).append(
                "action_cancelled",
                {
                    "action_id": action.action_id,
                    "checkpoint_id": checkpoint["checkpoint_id"],
                },
            )
            raise
        except Exception as exc:
            if action.action_id not in session.failed_actions:
                session.failed_actions.append(action.action_id)
            session.state = SessionState.FAILED
            self._save(session)
            self._ledger(session).append(
                "action_failed",
                {"action_id": action.action_id, "error_type": type(exc).__name__},
            )
            raise
        finally:
            self._cancel_events.pop(session.session_id, None)
            self._running_actions.pop(session.session_id, None)

    def create_checkpoint(self, session: SupervisorSession, *, label: str = "manual") -> dict[str, Any]:
        manifest = file_manifest(session.workspace)
        checkpoint_id = f"checkpoint_{digest({'manifest': manifest, 'label': label})[:24]}"
        root = session.root / "checkpoints" / checkpoint_id
        if not root.exists():
            root.mkdir(parents=True)
            copy_verified_tree(session.workspace, root / "files")
            _atomic_json(root / "manifest.json", manifest)
            _atomic_json(root / "metadata.json", {"checkpoint_id": checkpoint_id, "label": label, "created_at": _now()})
        self._ledger(session).append(
            "checkpoint_created",
            {"checkpoint_id": checkpoint_id, "label": label, "manifest_hash": digest(manifest)},
        )
        return {"checkpoint_id": checkpoint_id, "manifest": manifest}

    def diff(self, session: SupervisorSession) -> dict[str, Any]:
        initial = json.loads((session.control / "initial-manifest.json").read_text(encoding="utf-8"))
        current = file_manifest(session.workspace)
        return manifest_diff(initial, current)

    def pause(self, session: SupervisorSession) -> None:
        self._require_active(session)
        session.state = SessionState.PAUSED
        self._save(session)
        self._ledger(session).append("session_paused", {})

    def resume(self, session: SupervisorSession) -> None:
        if session.state not in {SessionState.PAUSED, SessionState.FAILED}:
            raise SupervisorError("only a paused or failed session can resume")
        session.state = SessionState.WAITING_APPROVAL if session.queued_actions else SessionState.CREATED
        self._save(session)
        self._ledger(session).append("session_resumed", {})

    def cancel(self, session: SupervisorSession) -> None:
        if session.state == SessionState.CANDIDATE_READY:
            raise SupervisorError("a completed candidate cannot be cancelled")
        if session.state == SessionState.CANCELLING:
            return
        if session.state == SessionState.RUNNING:
            event = self._cancel_events.get(session.session_id)
            action_id = self._running_actions.get(session.session_id)
            if event is None or action_id is None:
                raise SupervisorError("the active process is not attached to this supervisor")
            session.state = SessionState.CANCELLING
            self._save(session)
            self._ledger(session).append(
                "session_cancel_requested", {"action_id": action_id}
            )
            event.set()
            return
        session.state = SessionState.CANCELLED
        self._save(session)
        self._ledger(session).append("session_cancelled", {})

    def finalize_candidate(self, session: SupervisorSession) -> Path:
        if session.state in {
            SessionState.CANCELLED,
            SessionState.FAILED,
            SessionState.RUNNING,
            SessionState.CANCELLING,
        }:
            raise SupervisorError("session is not eligible for candidate review")
        remaining = set(session.queued_actions) - set(session.completed_actions)
        if remaining:
            raise SupervisorError("all queued actions must be completed before review")
        ledger_status = self._ledger(session).verify()
        changes = self.diff(session)
        candidate = {
            "schema_version": "1.0",
            "session_id": session.session_id,
            "pack_id": session.pack_id,
            "pack_content_hash": session.pack_content_hash,
            "state": SessionState.CANDIDATE_READY.value,
            "changes": changes,
            "usage": session.usage.public(),
            "ledger_head": ledger_status["head"],
            "execution_policy": self.execution_policy.policy_name,
            "cancelled_actions": list(session.cancelled_actions),
            "review_required": True,
            "published": False,
        }
        path = session.control / "candidate.json"
        _atomic_json(path, candidate)
        session.state = SessionState.CANDIDATE_READY
        self._save(session)
        self._ledger(session).append(
            "candidate_ready",
            {"candidate_hash": digest(candidate), "review_required": True},
        )
        return path

    def _write_text(self, session: SupervisorSession, action: ActionProposal) -> dict[str, Any]:
        path = safe_workspace_path(session.workspace, str(action.parameters.get("path", "")))
        text = action.parameters.get("text")
        if not isinstance(text, str):
            raise SupervisorError("write action text must be a string")
        data = text.encode("utf-8")
        if session.usage.written_files + 1 > session.budgets.max_written_files:
            raise SupervisorError("file-write budget exceeded")
        if session.usage.written_bytes + len(data) > session.budgets.max_written_bytes:
            raise SupervisorError("written-byte budget exceeded")
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_bytes(data)
        os.replace(temporary, path)
        session.usage.written_files += 1
        session.usage.written_bytes += len(data)
        return {
            "operation": action.operation.value,
            "path": path.relative_to(session.workspace).as_posix(),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }

    def _run_process(
        self,
        session: SupervisorSession,
        action: ActionProposal,
        checkpoint: Mapping[str, Any],
        cancel_event: threading.Event,
        isolation: IsolationAssessment,
    ) -> dict[str, Any]:
        parameters = action.parameters
        argv = parameters.get("argv")
        if not isinstance(argv, list) or not argv or len(argv) > MAX_ARG_COUNT:
            raise SupervisorError("process argv is invalid")
        if any(not isinstance(item, str) or not item or len(item) > MAX_ARG_CHARS for item in argv):
            raise SupervisorError("process argv contains an invalid argument")
        if action.operation == ActionOperation.GIT_COMMAND:
            self._validate_local_git(argv, action)
        timeout = float(parameters.get("timeout_seconds", 300.0))
        if timeout <= 0 or session.usage.process_seconds + timeout > session.budgets.max_process_seconds:
            raise SupervisorError("process-time budget exceeded")
        cwd_relative = str(parameters.get("cwd", "."))
        cwd = session.workspace if cwd_relative == "." else safe_workspace_path(session.workspace, cwd_relative)
        if not cwd.is_dir():
            raise SupervisorError("process working directory is missing")
        env = self._process_environment(action)
        before = file_manifest(session.workspace)
        started = time.monotonic()
        try:
            runner_arguments = {
                "cwd": str(cwd),
                "input_text": str(parameters.get("stdin_text", "")),
                "timeout": timeout,
                "env": env,
            }
            if self._uses_default_runner:
                runner_arguments["cancel_event"] = cancel_event
            completed = self.process_runner(argv, **runner_arguments)
            if cancel_event.is_set():
                raise ProcessCancelledError(
                    "approved process was cancelled; checkpoint restored"
                )
        except ProcessCancelledError:
            self._restore_checkpoint(session, str(checkpoint["checkpoint_id"]))
            raise
        except subprocess.TimeoutExpired as exc:
            self._restore_checkpoint(session, str(checkpoint["checkpoint_id"]))
            raise SupervisorError(f"approved process timed out after {timeout:g} seconds") from exc
        except Exception:
            self._restore_checkpoint(session, str(checkpoint["checkpoint_id"]))
            raise
        elapsed = time.monotonic() - started
        session.usage.process_seconds += elapsed
        if Capability.NETWORK in action.capabilities:
            session.usage.network_actions += 1
        if Capability.EXTERNAL_ACTION in action.capabilities:
            session.usage.external_actions += 1
        try:
            after = file_manifest(session.workspace)
        except SupervisorError as exc:
            self._restore_checkpoint(session, str(checkpoint["checkpoint_id"]))
            raise SupervisorError(
                "process produced an unsafe or oversized workspace; checkpoint restored"
            ) from exc
        changes = manifest_diff(before, after)
        changed_paths = changes["added"] + changes["modified"] + changes["deleted"]
        if changed_paths and Capability.FILE_WRITE not in action.capabilities:
            self._restore_checkpoint(session, str(checkpoint["checkpoint_id"]))
            raise SupervisorError("process changed files without file-write approval; workspace was restored")
        written = sum(after[path]["size"] for path in changes["added"] + changes["modified"])
        if changed_paths:
            if session.usage.written_files + len(changed_paths) > session.budgets.max_written_files or session.usage.written_bytes + written > session.budgets.max_written_bytes:
                self._restore_checkpoint(session, str(checkpoint["checkpoint_id"]))
                raise SupervisorError("process exceeded the file-write budget; workspace was restored")
            session.usage.written_files += len(changed_paths)
            session.usage.written_bytes += written
        stdout = redact_secrets(completed.stdout[:MAX_PROCESS_OUTPUT_CHARS])
        stderr = redact_secrets(completed.stderr[:MAX_PROCESS_OUTPUT_CHARS])
        log = {
            "action_id": action.action_id,
            "returncode": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "elapsed_seconds": round(elapsed, 6),
            "changed_paths": changed_paths,
            "isolation": isolation.public(),
        }
        _atomic_json(session.control / "logs" / f"{action.action_id}.json", log)
        if completed.returncode != 0:
            self._restore_checkpoint(session, str(checkpoint["checkpoint_id"]))
            raise SupervisorError(f"approved process exited with status {completed.returncode}")
        return {
            "operation": action.operation.value,
            "returncode": completed.returncode,
            "elapsed_seconds": round(elapsed, 6),
            "changed_paths": changed_paths,
            "isolation": isolation.public(),
            "log": f"control/logs/{action.action_id}.json",
        }

    def _process_environment(self, action: ActionProposal) -> dict[str, str]:
        allowed = {
            "PATH", "PATHEXT", "SystemRoot", "WINDIR", "COMSPEC", "TEMP", "TMP",
            "USERPROFILE", "HOME", "LOCALAPPDATA", "APPDATA", "LANG", "LC_ALL",
        }
        env = {key: value for key, value in os.environ.items() if key in allowed}
        requested = action.parameters.get("credential_env", [])
        if requested:
            if Capability.CREDENTIALS not in action.capabilities:
                raise SupervisorError("credential environment access was not declared")
            if not isinstance(requested, list) or any(not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", str(name)) for name in requested):
                raise SupervisorError("credential environment allow-list is invalid")
            for name in requested:
                if name in os.environ:
                    env[name] = os.environ[name]
        if Capability.NETWORK not in action.capabilities:
            blocked = "http://127.0.0.1:9"
            env.update({"HTTP_PROXY": blocked, "HTTPS_PROXY": blocked, "ALL_PROXY": blocked, "NO_PROXY": ""})
        return env

    def _validate_local_git(self, argv: Sequence[str], action: ActionProposal) -> None:
        if Path(argv[0]).name.lower() not in {"git", "git.exe"}:
            raise SupervisorError("git actions must invoke the git executable")
        network_commands = {"push", "pull", "fetch", "clone", "ls-remote", "submodule"}
        command = next((item for item in argv[1:] if not item.startswith("-")), "")
        if command in network_commands and Capability.NETWORK not in action.capabilities:
            raise SupervisorError("network-capable Git action requires network approval")

    def _check_budget_before(self, session: SupervisorSession, action: ActionProposal) -> None:
        if session.usage.actions >= session.budgets.max_actions:
            raise SupervisorError("action budget exhausted")
        if Capability.NETWORK in action.capabilities and session.usage.network_actions >= session.budgets.max_network_actions:
            raise SupervisorError("network-action budget exhausted")
        if Capability.EXTERNAL_ACTION in action.capabilities and session.usage.external_actions >= session.budgets.max_external_actions:
            raise SupervisorError("external-action budget exhausted")

    def _restore_checkpoint(self, session: SupervisorSession, checkpoint_id: str) -> None:
        source = session.root / "checkpoints" / checkpoint_id / "files"
        if not source.is_dir():
            raise SupervisorError("checkpoint files are missing")
        for child in session.workspace.iterdir():
            if child.is_symlink() or child.is_file():
                child.unlink()
            else:
                shutil.rmtree(child)
        copy_verified_tree(source, session.workspace)
        self._ledger(session).append("checkpoint_restored", {"checkpoint_id": checkpoint_id})

    def _load_action(self, session: SupervisorSession, action_id: str) -> ActionProposal:
        if action_id not in session.queued_actions:
            raise SupervisorError("action is not queued in this session")
        try:
            value = json.loads((session.control / "actions" / f"{action_id}.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise SupervisorError("action proposal is missing or invalid") from exc
        return ActionProposal.from_public(value)

    def _load_approval(self, session: SupervisorSession, action: ActionProposal) -> ApprovalGrant:
        path = session.control / "approvals" / f"{action.action_id}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise SupervisorError("action has no valid approval") from exc
        content = {
            "session_id": value.get("session_id"),
            "action_id": value.get("action_id"),
            "capabilities": value.get("capabilities"),
            "actor": value.get("actor"),
            "approved_at": value.get("approved_at"),
        }
        if value.get("approval_id") != f"grant_{digest(content)[:24]}" or content["session_id"] != session.session_id or content["action_id"] != action.action_id:
            raise SupervisorError("action approval is stale or tampered")
        approved_ids = {
            item.get("details", {}).get("approval_id")
            for item in self._ledger(session).entries()
            if item.get("event") == "action_approved"
        }
        if value.get("approval_id") not in approved_ids:
            raise SupervisorError("action approval is not recorded in the ledger")
        return ApprovalGrant(
            str(value["approval_id"]), session.session_id, action.action_id,
            tuple(Capability(item) for item in value["capabilities"]),
            str(value["actor"]), str(value["approved_at"]),
        )

    def _require_active(self, session: SupervisorSession) -> None:
        self.entitlement.require(ProductCapability.SUPERVISED_BUILD)
        if session.state in {
            SessionState.CANCELLED,
            SessionState.CANDIDATE_READY,
            SessionState.RUNNING,
            SessionState.CANCELLING,
        }:
            raise SupervisorError(f"session is not editable while {session.state.value}")

    def _save(self, session: SupervisorSession) -> None:
        _atomic_json(session.control / "session.json", session.public())

    def _ledger(self, session: SupervisorSession) -> AppendOnlyLedger:
        return AppendOnlyLedger(session.control / "ledger.jsonl")
