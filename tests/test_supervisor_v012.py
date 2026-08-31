from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

from relic_auditor.product_discovery.entitlements import entitlement_for_testing
from relic_auditor.supervisor import (
    ExecutionBoundary,
    ExecutionPolicy,
    ProcessCancelledError,
    SessionState,
    StaticAdapter,
    SupervisorError,
    SupervisorService,
    assess_action_isolation,
    claude_builder_action,
    codex_builder_action,
    process_action,
)
from relic_auditor.supervisor.ledger import AppendOnlyLedger

from test_supervisor_v011 import _exported_pack


PREMIUM = entitlement_for_testing("premium")


def test_ledger_serializes_concurrent_appends(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledgers = [AppendOnlyLedger(path) for _ in range(8)]
    errors: list[BaseException] = []

    def append_batch(ledger: AppendOnlyLedger, worker: int) -> None:
        try:
            for item in range(12):
                ledger.append("concurrent_test", {"worker": worker, "item": item})
        except BaseException as exc:
            errors.append(exc)

    workers = [
        threading.Thread(target=append_batch, args=(ledger, number))
        for number, ledger in enumerate(ledgers)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)

    assert not errors
    assert all(not worker.is_alive() for worker in workers)
    status = ledgers[0].verify()
    assert status["valid"] is True
    assert status["entries"] == 96


def test_production_policy_accepts_only_exact_codex_profile() -> None:
    action = codex_builder_action(model="gpt-5.5")
    assessment = ExecutionPolicy.production().require(action)
    assert assessment.boundary == ExecutionBoundary.PROVIDER_SANDBOX
    assert assessment.enforced is True
    assert assessment.production_supported is True


def test_codex_profile_with_extra_sandbox_argument_is_rejected() -> None:
    action = codex_builder_action()
    action.parameters["argv"].extend(["--sandbox", "danger-full-access"])
    assessment = assess_action_isolation(action)
    assert assessment.enforced is False
    with pytest.raises(SupervisorError, match="incomplete or altered"):
        ExecutionPolicy.production().require(action)


def test_production_policy_blocks_native_and_claude_processes() -> None:
    native = process_action(["builder"], summary="Native builder", writes_files=True)
    claude = claude_builder_action()
    with pytest.raises(SupervisorError, match="operating-system authority"):
        ExecutionPolicy.production().require(native)
    with pytest.raises(SupervisorError, match="not an OS isolation boundary"):
        ExecutionPolicy.production().require(claude)


def test_default_runner_cancellation_kills_process_and_restores_checkpoint(
    tmp_path: Path,
) -> None:
    _, pack = _exported_pack(tmp_path)
    service = SupervisorService(
        PREMIUM,
        execution_policy=ExecutionPolicy.testing(),
    )
    session = service.create_session(pack, tmp_path / "sessions")
    script = (
        "from pathlib import Path; import time; "
        "Path('partial.txt').write_text('partial', encoding='utf-8'); "
        "time.sleep(60)"
    )
    action = process_action(
        [sys.executable, "-c", script],
        summary="Cancelable native test process",
        timeout_seconds=65,
        writes_files=True,
    )
    service.plan(session, StaticAdapter((action,)))
    service.approve(session, action.action_id, action.capabilities, actor="operator")
    observed: list[BaseException] = []

    def execute() -> None:
        try:
            service.execute(session, action.action_id)
        except BaseException as exc:  # captured for assertion in the test thread
            observed.append(exc)

    worker = threading.Thread(target=execute, daemon=True)
    started = time.monotonic()
    worker.start()
    while session.state != SessionState.RUNNING and worker.is_alive():
        if time.monotonic() - started > 5:
            pytest.fail("supervised process did not start")
        time.sleep(0.01)
    service.cancel(session)
    assert session.state == SessionState.CANCELLING
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert len(observed) == 1
    assert isinstance(observed[0], ProcessCancelledError)
    assert session.state == SessionState.CANCELLED
    assert session.cancelled_actions == [action.action_id]
    assert not (session.workspace / "partial.txt").exists()
    assert service.load_session(session.root).cancelled_actions == [action.action_id]
