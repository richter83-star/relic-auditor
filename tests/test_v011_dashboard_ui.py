from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from relic_auditor.audit import audit_estate
from relic_auditor.build_packs import BuildPackService
from relic_auditor.dashboard.license_dialog import LicenseDialog
from relic_auditor.dashboard.supervisor_dialog import AssistedBuildDialog
from relic_auditor.product_discovery.entitlements import (
    FREE_ENTITLEMENT,
    entitlement_for_testing,
)


PREMIUM = entitlement_for_testing("premium")


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _exported_pack(tmp_path: Path) -> Path:
    estate = tmp_path / "estate"
    (estate / "src").mkdir(parents=True)
    (estate / "LICENSE").write_text("MIT License", encoding="utf-8")
    (estate / "src" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    audit = audit_estate(estate)
    record = next(item for item in audit.files if item.path == "src/core.py")
    opportunity = {
        "opportunity_id": "opp_v011_ui",
        "title": "Guided product",
        "summary": "Verify the v0.11 guided build path.",
        "evidence": ["ev_a", "ev_b"],
        "evidence_score": 85,
        "technical_verification_status": "moderate",
        "reusable_assets": [
            {
                "path": record.path,
                "sha256": record.sha256,
                "evidence": ["ev_a"],
            }
        ],
        "missing_components": ["Tests"],
    }
    service = BuildPackService(PREMIUM)
    pack = service.prepare(
        {"opportunities": [opportunity]},
        "opp_v011_ui",
        audit=audit,
        source_root=estate,
    )
    approval = service.approve(pack, ["src/core.py"])
    return service.export(pack, approval, tmp_path / "packs").directory


def test_supervisor_has_five_steps_and_no_preapproved_capabilities(tmp_path: Path) -> None:
    app = _app()
    pack = _exported_pack(tmp_path)
    with patch("relic_auditor.dashboard.supervisor_dialog.shutil.which", return_value="C:/tools/codex.exe"):
        dialog = AssistedBuildDialog(PREMIUM, pack, tmp_path / "sessions")
        assert dialog.stack.count() == 5
        assert dialog.step_label.text().startswith("Step 1 of 5")
        dialog.next_step()
        assert dialog.stack.currentIndex() == 1
        dialog.next_step()
        assert dialog.stack.currentIndex() == 2
        assert dialog.session is not None
        assert dialog.session.workspace != pack
        dialog.next_step()
        assert dialog.stack.currentIndex() == 3
        assert dialog.action is not None
        assert dialog.action_identity.text().find(dialog.action.action_id) >= 0
        assert dialog.action_identity.text().find("Exact command:") >= 0
        assert dialog._approval_checks
        assert all(not item.isChecked() for item in dialog._approval_checks)
        assert not dialog.next_button.isEnabled()
        for checkbox in dialog._approval_checks:
            checkbox.setCheckState(Qt.CheckState.Checked)
        app.processEvents()
        assert dialog.next_button.isEnabled()
        dialog.next_step()
        assert dialog.stack.currentIndex() == 4
        assert dialog.run_button.isEnabled()
        assert dialog.finalize_button.isEnabled() is False
        dialog.reject()
        assert not dialog.session.completed_actions
        dialog.deleteLater()
        app.processEvents()


def test_unprovisioned_license_ui_is_honest_and_disabled() -> None:
    app = _app()
    dialog = LicenseDialog(FREE_ENTITLEMENT)
    assert dialog.badge.text() == "PLAN: FREE"
    assert "not provisioned" in dialog.details.text()
    assert not dialog.activate_button.isEnabled()
    assert not dialog.deactivate_button.isEnabled()
    dialog.deleteLater()
    app.processEvents()
