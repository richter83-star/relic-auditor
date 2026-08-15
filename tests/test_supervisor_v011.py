from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from relic_auditor.audit import audit_estate
from relic_auditor.build_packs import BuildPackService
from relic_auditor.product_discovery.entitlements import (
    FREE_ENTITLEMENT,
    entitlement_for_testing,
)
from relic_auditor.supervisor import (
    BUILDER_PROMPT,
    ActionOperation,
    ActionProposal,
    AppendOnlyLedger,
    BudgetLimits,
    Capability,
    ProcessResult,
    SessionState,
    StaticAdapter,
    SupervisorError,
    SupervisorService,
    claude_builder_action,
    codex_builder_action,
    dependency_action,
    git_action,
    process_action,
    write_text_action,
)
from relic_auditor.supervisor.workspace import safe_workspace_path


PREMIUM = entitlement_for_testing("premium")


def _exported_pack(tmp_path: Path) -> tuple[Path, Path]:
    estate = tmp_path / "estate"
    (estate / "src").mkdir(parents=True)
    (estate / "LICENSE").write_text("MIT License", encoding="utf-8")
    (estate / "src" / "core.py").write_text(
        "def evaluate(value):\n    return value\n", encoding="utf-8"
    )
    audit = audit_estate(estate)
    record = next(item for item in audit.files if item.path == "src/core.py")
    opportunity = {
        "schema_version": "1.0",
        "opportunity_id": "opp_supervisor",
        "title": "Supervised fixture",
        "summary": "A bounded fixture for supervised-build verification.",
        "target_user": "Test operators",
        "job_to_be_done": "Verify safe managed builds.",
        "evidence": ["ev_core", "ev_plan"],
        "evidence_score": 85,
        "technical_verification_status": "moderate",
        "supporting_capability_ids": ["cap_core"],
        "reusable_assets": [
            {
                "path": "src/core.py",
                "sha256": record.sha256,
                "evidence": ["ev_core"],
            }
        ],
        "missing_components": ["Tests"],
        "risks": ["Fixture only"],
        "next_validation_steps": ["Run tests"],
    }
    build_packs = BuildPackService(PREMIUM)
    pack = build_packs.prepare(
        {"schema_version": "0.9", "opportunities": [opportunity]},
        "opp_supervisor",
        audit=audit,
        source_root=estate,
    )
    approval = build_packs.approve(pack, ["src/core.py"])
    exported = build_packs.export(pack, approval, tmp_path / "packs")
    return estate, exported.directory


def _session(tmp_path: Path, **kwargs):
    estate, pack = _exported_pack(tmp_path)
    service = SupervisorService(PREMIUM, **kwargs)
    session = service.create_session(pack, tmp_path / "sessions")
    return estate, pack, service, session


def test_free_tier_cannot_create_supervised_session(tmp_path: Path) -> None:
    _, pack = _exported_pack(tmp_path)
    with pytest.raises(PermissionError, match="higher Relic entitlement"):
        SupervisorService(FREE_ENTITLEMENT).create_session(pack, tmp_path / "sessions")


def test_session_is_isolated_and_seeds_only_approved_assets(tmp_path: Path) -> None:
    estate, pack, _, session = _session(tmp_path)
    assert session.workspace != estate.resolve()
    assert session.workspace != pack.resolve()
    assert (session.workspace / "src" / "core.py").is_file()
    assert (session.workspace / ".relic" / "build-pack" / "build-pack.json").is_file()
    assert not (session.root / "estate").exists()


def test_session_root_inside_original_scan_target_is_rejected(tmp_path: Path) -> None:
    estate, pack = _exported_pack(tmp_path)
    with pytest.raises(SupervisorError, match="outside the original scan target"):
        SupervisorService(PREMIUM).create_session(pack, estate / "build-sessions")


def test_reviewed_write_lifecycle_reaches_candidate(tmp_path: Path) -> None:
    _, _, service, session = _session(tmp_path)
    action = write_text_action("tests/test_core.py", "def test_core():\n    assert True\n")
    service.plan(session, StaticAdapter((action,)))
    service.approve(session, action.action_id, action.capabilities, actor="Brian")
    result = service.execute(session, action.action_id)
    assert result["path"] == "tests/test_core.py"
    assert (session.workspace / "tests" / "test_core.py").is_file()
    candidate = service.finalize_candidate(session)
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    assert payload["review_required"] is True
    assert payload["published"] is False
    assert service.load_session(session.root).state == SessionState.CANDIDATE_READY


def test_partial_capability_approval_fails_closed(tmp_path: Path) -> None:
    _, _, service, session = _session(tmp_path)
    action = process_action(["builder"], summary="Builder writes files", writes_files=True)
    service.plan(session, StaticAdapter((action,)))
    service.approve(session, action.action_id, [Capability.PROCESS], actor="operator")
    with pytest.raises(SupervisorError, match="not fully approved"):
        service.execute(session, action.action_id)


def test_unapproved_action_never_runs(tmp_path: Path) -> None:
    invoked = []

    def runner(*args, **kwargs):
        invoked.append((args, kwargs))
        return ProcessResult(0, "", "")

    _, _, service, session = _session(tmp_path, process_runner=runner)
    action = process_action(["builder"], summary="No approval")
    service.plan(session, StaticAdapter((action,)))
    with pytest.raises(SupervisorError, match="no valid approval"):
        service.execute(session, action.action_id)
    assert invoked == []


def test_process_file_write_without_capability_is_rolled_back(tmp_path: Path) -> None:
    def runner(argv, *, cwd, **kwargs):
        del argv, kwargs
        (Path(cwd) / "escaped.txt").write_text("not approved", encoding="utf-8")
        return ProcessResult(0, "ok", "")

    _, _, service, session = _session(tmp_path, process_runner=runner)
    action = process_action(["builder"], summary="Read-only process")
    service.plan(session, StaticAdapter((action,)))
    service.approve(session, action.action_id, action.capabilities, actor="operator")
    with pytest.raises(SupervisorError, match="without file-write approval"):
        service.execute(session, action.action_id)
    assert not (session.workspace / "escaped.txt").exists()
    assert (session.workspace / "src" / "core.py").is_file()


@pytest.mark.parametrize("failure", ["exception", "timeout", "nonzero"])
def test_failed_process_always_restores_checkpoint(tmp_path: Path, failure: str) -> None:
    def runner(argv, *, cwd, timeout, **kwargs):
        del argv, kwargs
        (Path(cwd) / "partial.txt").write_text("partial", encoding="utf-8")
        if failure == "exception":
            raise OSError("provider crashed")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(["builder"], timeout)
        return ProcessResult(7, "", "failed")

    _, _, service, session = _session(tmp_path, process_runner=runner)
    action = process_action(
        ["builder"], summary="Potentially partial build", writes_files=True
    )
    service.plan(session, StaticAdapter((action,)))
    service.approve(session, action.action_id, action.capabilities, actor="operator")
    with pytest.raises((OSError, SupervisorError)):
        service.execute(session, action.action_id)
    assert not (session.workspace / "partial.txt").exists()
    assert (session.workspace / "src" / "core.py").is_file()


def test_approved_process_changes_are_recorded(tmp_path: Path) -> None:
    observed = {}

    def runner(argv, *, cwd, env, **kwargs):
        del argv, kwargs
        observed.update(env)
        (Path(cwd) / "built.txt").write_text("candidate", encoding="utf-8")
        return ProcessResult(0, "finished", "")

    _, _, service, session = _session(tmp_path, process_runner=runner)
    action = process_action(["builder"], summary="Build candidate", writes_files=True)
    service.plan(session, StaticAdapter((action,)))
    service.approve(session, action.action_id, action.capabilities, actor="operator")
    result = service.execute(session, action.action_id)
    assert result["changed_paths"] == ["built.txt"]
    assert observed["HTTPS_PROXY"] == "http://127.0.0.1:9"
    assert session.usage.written_files == 1


def test_process_logs_are_secret_redacted(tmp_path: Path) -> None:
    def runner(*args, **kwargs):
        del args, kwargs
        return ProcessResult(0, "token sk-abcdefghijklmnop", "")

    _, _, service, session = _session(tmp_path, process_runner=runner)
    action = process_action(["builder"], summary="Redaction")
    service.plan(session, StaticAdapter((action,)))
    service.approve(session, action.action_id, action.capabilities, actor="operator")
    service.execute(session, action.action_id)
    log = (session.control / "logs" / f"{action.action_id}.json").read_text(encoding="utf-8")
    assert "sk-abcdefghijklmnop" not in log


def test_credentials_are_individually_declared(monkeypatch, tmp_path: Path) -> None:
    observed = {}

    def runner(*args, env, **kwargs):
        del args, kwargs
        observed.update(env)
        return ProcessResult(0, "", "")

    monkeypatch.setenv("RELIC_TEST_CREDENTIAL", "private")
    monkeypatch.setenv("UNDECLARED_SECRET", "never")
    _, _, service, session = _session(tmp_path, process_runner=runner)
    action = process_action(
        ["builder"],
        summary="Credential-gated operation",
        credential_env=["RELIC_TEST_CREDENTIAL"],
    )
    service.plan(session, StaticAdapter((action,)))
    service.approve(session, action.action_id, action.capabilities, actor="operator")
    service.execute(session, action.action_id)
    assert observed["RELIC_TEST_CREDENTIAL"] == "private"
    assert "UNDECLARED_SECRET" not in observed


def test_external_actions_default_to_zero_budget(tmp_path: Path) -> None:
    _, _, service, session = _session(tmp_path)
    action = ActionProposal.create(
        ActionOperation.EXTERNAL_ACTION,
        "Publish externally",
        [Capability.PROCESS, Capability.NETWORK, Capability.EXTERNAL_ACTION],
        {"argv": ["publisher"], "cwd": ".", "timeout_seconds": 30},
        risk="high",
    )
    service.plan(session, StaticAdapter((action,)))
    service.approve(session, action.action_id, action.capabilities, actor="operator")
    with pytest.raises(SupervisorError, match="external-action budget exhausted"):
        service.execute(session, action.action_id)


def test_dependency_action_requires_separate_high_risk_capabilities() -> None:
    action = dependency_action(["python", "-m", "pip", "install", "x"], summary="Install x")
    assert set(action.capabilities) == {
        Capability.PROCESS,
        Capability.DEPENDENCY_INSTALL,
        Capability.NETWORK,
    }
    assert action.risk == "high"


def test_codex_builder_is_ephemeral_workspace_write_and_explicitly_gated() -> None:
    action = codex_builder_action(model="gpt-5.5")
    assert set(action.capabilities) == {
        Capability.PROCESS,
        Capability.FILE_WRITE,
        Capability.NETWORK,
        Capability.CREDENTIALS,
    }
    argv = list(action.parameters["argv"])
    assert argv[:2] == ["codex", "exec"]
    assert "--ephemeral" in argv
    assert argv[argv.index("--sandbox") + 1] == "workspace-write"
    assert "--ignore-user-config" in argv
    assert "--ignore-rules" in argv
    assert "danger-full-access" not in argv
    assert "--full-auto" not in argv
    assert argv[-3:] == ["--model", "gpt-5.5", "-"]


def test_claude_builder_has_no_shell_or_mcp_tools_and_is_explicitly_gated() -> None:
    action = claude_builder_action(model="sonnet", effort="high")
    assert set(action.capabilities) == {
        Capability.PROCESS,
        Capability.FILE_WRITE,
        Capability.NETWORK,
        Capability.CREDENTIALS,
    }
    argv = list(action.parameters["argv"])
    assert argv[:2] == ["claude", "-p"]
    assert "--safe-mode" in argv
    assert "--no-session-persistence" in argv
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert argv[argv.index("--tools") + 1] == "Read,Glob,Grep,Write,Edit"
    assert "Bash" not in " ".join(argv)
    assert "--dangerously-skip-permissions" not in argv


def test_builder_prompt_forbids_automatic_release_or_dependency_actions() -> None:
    prompt = BUILDER_PROMPT.lower()
    assert "do not publish" in prompt
    assert "deploy" in prompt
    assert "install dependencies" in prompt
    assert "git remotes" in prompt


def test_network_git_is_rejected_without_network_capability(tmp_path: Path) -> None:
    _, _, service, session = _session(
        tmp_path, process_runner=lambda *a, **k: ProcessResult(0, "", "")
    )
    action = git_action(["git", "push", "origin", "HEAD"], summary="Push")
    service.plan(session, StaticAdapter((action,)))
    service.approve(session, action.action_id, action.capabilities, actor="operator")
    with pytest.raises(SupervisorError, match="network approval"):
        service.execute(session, action.action_id)


def test_path_traversal_write_is_rejected(tmp_path: Path) -> None:
    _, _, service, session = _session(tmp_path)
    action = write_text_action("../outside.txt", "escape")
    service.plan(session, StaticAdapter((action,)))
    service.approve(session, action.action_id, action.capabilities, actor="operator")
    with pytest.raises(ValueError):
        service.execute(session, action.action_id)
    assert not (session.root.parent / "outside.txt").exists()


def test_symlink_parent_is_rejected_before_creating_outside_directories(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (workspace / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable on this platform")
    with pytest.raises(SupervisorError, match="symbolic link"):
        safe_workspace_path(workspace, "link/new/file.txt")
    assert not (outside / "new").exists()


def test_action_tampering_is_detected(tmp_path: Path) -> None:
    _, _, service, session = _session(tmp_path)
    action = write_text_action("new.txt", "safe")
    service.plan(session, StaticAdapter((action,)))
    path = session.control / "actions" / f"{action.action_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["parameters"]["text"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SupervisorError, match="identity"):
        service.list_actions(session)


def test_approval_tampering_is_detected(tmp_path: Path) -> None:
    _, _, service, session = _session(tmp_path)
    action = write_text_action("new.txt", "safe")
    service.plan(session, StaticAdapter((action,)))
    service.approve(session, action.action_id, action.capabilities, actor="operator")
    approval = session.control / "approvals" / f"{action.action_id}.json"
    payload = json.loads(approval.read_text(encoding="utf-8"))
    payload["actor"] = "tampered"
    approval.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SupervisorError, match="tampered"):
        service.execute(session, action.action_id)


def test_session_action_list_tampering_is_detected(tmp_path: Path) -> None:
    _, _, service, session = _session(tmp_path)
    state = session.control / "session.json"
    payload = json.loads(state.read_text(encoding="utf-8"))
    payload["queued_actions"] = ["action_" + "0" * 24]
    state.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SupervisorError, match="does not match its ledger"):
        service.load_session(session.root)


def test_ledger_tampering_is_detected(tmp_path: Path) -> None:
    _, _, _, session = _session(tmp_path)
    ledger = AppendOnlyLedger(session.control / "ledger.jsonl")
    path = ledger.path
    payload = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    payload["event"] = "changed"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises(SupervisorError, match="hash"):
        ledger.verify()


def test_pause_resume_cancel_are_explicit(tmp_path: Path) -> None:
    _, _, service, session = _session(tmp_path)
    service.pause(session)
    assert session.state == SessionState.PAUSED
    service.resume(session)
    assert session.state == SessionState.CREATED
    service.cancel(session)
    assert session.state == SessionState.CANCELLED
    with pytest.raises(SupervisorError, match="not editable"):
        service.plan(session, StaticAdapter((write_text_action("x", "x"),)))


def test_budget_rejects_plan_before_execution(tmp_path: Path) -> None:
    estate, pack = _exported_pack(tmp_path)
    del estate
    service = SupervisorService(PREMIUM)
    session = service.create_session(pack, tmp_path / "sessions", budgets=BudgetLimits(max_actions=1))
    actions = (write_text_action("one", "1"), write_text_action("two", "2"))
    with pytest.raises(SupervisorError, match="action plan exceeds"):
        service.plan(session, StaticAdapter(actions))


def test_build_pack_and_original_estate_remain_unchanged(tmp_path: Path) -> None:
    estate, pack, service, session = _session(tmp_path)
    before_estate = (estate / "src" / "core.py").read_bytes()
    before_pack = (pack / "build-pack.json").read_bytes()
    action = write_text_action("src/core.py", "changed only in managed workspace\n")
    service.plan(session, StaticAdapter((action,)))
    service.approve(session, action.action_id, action.capabilities, actor="operator")
    service.execute(session, action.action_id)
    assert (estate / "src" / "core.py").read_bytes() == before_estate
    assert (pack / "build-pack.json").read_bytes() == before_pack
