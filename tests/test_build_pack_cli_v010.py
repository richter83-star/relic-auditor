from __future__ import annotations

import json
from pathlib import Path

from relic_auditor.audit import audit_estate
from relic_auditor.cli import main
from relic_auditor.product_discovery.entitlements import entitlement_for_testing


PREMIUM = entitlement_for_testing("premium")


def _fixture(tmp_path: Path):
    target = tmp_path / "estate"
    (target / "src").mkdir(parents=True)
    (target / "LICENSE").write_text("MIT License", encoding="utf-8")
    (target / "src" / "core.py").write_text(
        "def core():\n    return True\n", encoding="utf-8"
    )
    audit = audit_estate(target)
    record = next(record for record in audit.files if record.path == "src/core.py")
    report = tmp_path / "opportunities.json"
    report.write_text(
        json.dumps(
            {
                "schema_version": "0.9",
                "opportunities": [
                    {
                        "opportunity_id": "opp_cli",
                        "title": "CLI product",
                        "summary": "A bounded CLI product.",
                        "evidence": ["ev_a", "ev_b"],
                        "evidence_score": 80,
                        "technical_verification_status": "moderate",
                        "reusable_assets": [
                            {
                                "path": "src/core.py",
                                "sha256": record.sha256,
                                "evidence": ["ev_a"],
                            }
                        ],
                        "missing_components": ["Integration test"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return target, report


def test_01_free_cli_rejects_without_premium_leakage(tmp_path: Path, capsys):
    _, report = _fixture(tmp_path)
    assert main(["build-pack", "list", str(report), "--json"]) == 2
    captured = capsys.readouterr()
    assert "requires a higher Relic entitlement" in captured.err
    assert "src/core.py" not in captured.err + captured.out


def test_02_list_returns_only_opportunity_summary(tmp_path: Path, capsys):
    _, report = _fixture(tmp_path)
    assert main(["build-pack", "list", str(report), "--json"], entitlement=PREMIUM) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["opportunities"][0]["opportunity_id"] == "opp_cli"
    assert "reusable_assets" not in payload["opportunities"][0]


def test_03_status_is_machine_readable(tmp_path: Path, capsys):
    _, report = _fixture(tmp_path)
    assert (
        main(
            ["build-pack", "status", str(report), "--opportunity", "opp_cli", "--json"],
            entitlement=PREMIUM,
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["readiness"] == "eligible"


def test_04_preview_does_not_copy_assets(tmp_path: Path, capsys):
    target, report = _fixture(tmp_path)
    preview = tmp_path / "preview.json"
    assert (
        main(
            [
                "build-pack",
                "prepare",
                str(report),
                "--opportunity",
                "opp_cli",
                "--target",
                str(target),
                "--output",
                str(preview),
                "--json",
            ],
            entitlement=PREMIUM,
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["assets_copied"] is False
    assert preview.is_file() and not (tmp_path / "assets").exists()


def test_05_preview_approval_export_validate_lifecycle(tmp_path: Path, capsys):
    target, report = _fixture(tmp_path)
    preview = tmp_path / "preview.json"
    approval = tmp_path / "approval.json"
    exports = tmp_path / "exports"
    prepare_args = [
        "build-pack",
        "prepare",
        str(report),
        "--opportunity",
        "opp_cli",
        "--target",
        str(target),
        "--output",
        str(preview),
        "--approval-output",
        str(approval),
        "--approve",
        "src/core.py",
        "--json",
    ]
    assert main(prepare_args, entitlement=PREMIUM) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "build-pack",
                "export",
                str(preview),
                "--approval",
                str(approval),
                "--target",
                str(target),
                "--output",
                str(exports),
                "--json",
            ],
            entitlement=PREMIUM,
        )
        == 0
    )
    exported = Path(json.loads(capsys.readouterr().out)["directory"])
    assert (
        main(["build-pack", "validate", str(exported), "--json"], entitlement=PREMIUM)
        == 0
    )
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_06_stale_approval_is_rejected(tmp_path: Path, capsys):
    target, report = _fixture(tmp_path)
    preview = tmp_path / "preview.json"
    approval = tmp_path / "approval.json"
    assert (
        main(
            [
                "build-pack",
                "prepare",
                str(report),
                "--opportunity",
                "opp_cli",
                "--target",
                str(target),
                "--output",
                str(preview),
                "--approval-output",
                str(approval),
                "--approve",
                "src/core.py",
            ],
            entitlement=PREMIUM,
        )
        == 0
    )
    capsys.readouterr()
    (target / "src" / "core.py").write_text("changed = True\n", encoding="utf-8")
    assert (
        main(
            [
                "build-pack",
                "export",
                str(preview),
                "--approval",
                str(approval),
                "--target",
                str(target),
                "--output",
                str(tmp_path / "exports"),
            ],
            entitlement=PREMIUM,
        )
        == 2
    )
    assert "changed" in capsys.readouterr().err


def test_07_historical_status_requires_rescan(tmp_path: Path, capsys):
    report = tmp_path / "old.json"
    report.write_text(
        json.dumps(
            {
                "schema_version": "0.8",
                "opportunities": [
                    {
                        "opportunity_id": "opp_old",
                        "title": "Old",
                        "evidence": ["a", "b"],
                        "evidence_score": 70,
                        "extraction_plan": {"reuse": ["old.py"]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert (
        main(
            ["build-pack", "status", str(report), "--opportunity", "opp_old", "--json"],
            entitlement=PREMIUM,
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["rescan_required_for_assets"] is True
