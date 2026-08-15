from __future__ import annotations

import json
from pathlib import Path

from relic_auditor.audit import audit_estate
from relic_auditor.build_packs import BuildPackService
from relic_auditor.cli import main
from relic_auditor.product_discovery.entitlements import entitlement_for_testing


PREMIUM = entitlement_for_testing("premium")


def _pack(tmp_path: Path) -> Path:
    estate = tmp_path / "estate"
    (estate / "src").mkdir(parents=True)
    (estate / "LICENSE").write_text("MIT License", encoding="utf-8")
    (estate / "src" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    audit = audit_estate(estate)
    record = next(item for item in audit.files if item.path == "src/core.py")
    opportunity = {
        "schema_version": "1.0",
        "opportunity_id": "opp_cli_supervisor",
        "title": "CLI supervised build",
        "summary": "Test the complete approval-gated CLI lifecycle.",
        "target_user": "Operators",
        "job_to_be_done": "Build safely.",
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
        "risks": ["Fixture"],
        "next_validation_steps": ["Run tests"],
    }
    service = BuildPackService(PREMIUM)
    prepared = service.prepare(
        {"schema_version": "0.9", "opportunities": [opportunity]},
        "opp_cli_supervisor",
        audit=audit,
        source_root=estate,
    )
    approval = service.approve(prepared, ["src/core.py"])
    return service.export(prepared, approval, tmp_path / "packs").directory


def _json_output(capsys) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)


def test_free_cli_cannot_start_supervised_build(tmp_path: Path, capsys) -> None:
    pack = _pack(tmp_path)
    code = main(
        ["build", "start", str(pack), "--sessions", str(tmp_path / "sessions"), "--json"]
    )
    assert code == 2
    assert "higher Relic entitlement" in capsys.readouterr().err


def test_reviewed_cli_plan_approval_run_diff_and_finalize(tmp_path: Path, capsys) -> None:
    pack = _pack(tmp_path)
    sessions = tmp_path / "sessions"
    assert (
        main(
            ["build", "start", str(pack), "--sessions", str(sessions), "--json"],
            entitlement=PREMIUM,
        )
        == 0
    )
    session = Path(str(_json_output(capsys)["directory"]))

    plan = tmp_path / "reviewed-plan.json"
    plan.write_text(
        json.dumps(
            {
                "actions": [
                    {
                        "operation": "write_text",
                        "summary": "Add reviewed test",
                        "capabilities": ["file_write"],
                        "parameters": {
                            "path": "tests/test_candidate.py",
                            "text": "def test_candidate():\n    assert True\n",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    assert (
        main(
            ["build", "plan", str(session), "--file", str(plan), "--json"],
            entitlement=PREMIUM,
        )
        == 0
    )
    action_id = str(_json_output(capsys)["queued"][0]["action_id"])

    assert (
        main(
            [
                "build",
                "approve",
                str(session),
                "--action",
                action_id,
                "--capability",
                "file_write",
                "--actor",
                "test-operator",
                "--json",
            ],
            entitlement=PREMIUM,
        )
        == 0
    )
    assert _json_output(capsys)["action_id"] == action_id

    assert (
        main(
            ["build", "run", str(session), "--action", action_id, "--json"],
            entitlement=PREMIUM,
        )
        == 0
    )
    assert _json_output(capsys)["path"] == "tests/test_candidate.py"
    assert (session / "workspace" / "tests" / "test_candidate.py").is_file()

    assert main(["build", "diff", str(session), "--json"], entitlement=PREMIUM) == 0
    diff = _json_output(capsys)
    assert "tests/test_candidate.py" in diff["added"]

    assert (
        main(["build", "finalize", str(session), "--json"], entitlement=PREMIUM)
        == 0
    )
    finalized = _json_output(capsys)
    assert finalized["state"] == "candidate_ready"
    candidate = json.loads(Path(str(finalized["candidate"])).read_text(encoding="utf-8"))
    assert candidate["review_required"] is True
    assert candidate["published"] is False
