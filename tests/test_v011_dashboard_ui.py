from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit

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


def test_plan_ui_offers_offline_activation_and_pricing() -> None:
    app = _app()
    dialog = LicenseDialog(FREE_ENTITLEMENT)
    assert dialog.badge.text() == "PLAN: FREE"
    assert "reports and history" in dialog.details.text()
    assert "COMING SOON" in dialog.pro_card.title_label.text()
    assert "COMING SOON" in dialog.premium_card.title_label.text()
    assert dialog.findChildren(QLineEdit) == []
    assert not hasattr(dialog, "activate_button")
    assert dialog.import_button.isEnabled()
    assert dialog.deactivate_button.isHidden()
    with patch("relic_auditor.dashboard.license_dialog.QDesktopServices.openUrl", return_value=True) as opener:
        dialog.pricing_button.click()
        assert opener.call_args.args[0].toString().endswith("/docs/pricing.md")
    dialog.deleteLater()
    app.processEvents()


def test_plan_import_updates_window_and_deactivation_restores_free(tmp_path: Path) -> None:
    import json
    from datetime import UTC, datetime
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from test_licensing_v011 import DEVICE, MemoryStore, _token
    from relic_auditor.dashboard.qt_app import RelicWindow
    app = _app()
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    store = MemoryStore()
    path = tmp_path / "owner.json"
    path.write_text(json.dumps(_token(private, now=datetime.now(UTC))))
    window = RelicWindow(entitlement=FREE_ENTITLEMENT)
    dialog = LicenseDialog(FREE_ENTITLEMENT, store=store, public_keys={"test-key": public}, device_id=DEVICE)
    dialog.entitlement_changed.connect(window._entitlement_changed)
    dialog.copy_device_button.click()
    assert QApplication.clipboard().text() == DEVICE
    assert dialog.apply_license_file(path)
    assert dialog.badge.text() == "PLAN: PREMIUM"
    assert window.plan_badge.text() == "PLAN: PREMIUM"
    assert window.entitlement.tier.value == "premium"
    path.write_text("invalid")
    assert not dialog.apply_license_file(path)
    assert window.entitlement.tier.value == "premium"
    dialog.remove_license()
    assert store.value is None
    assert window.plan_badge.text() == "PLAN: FREE"
    dialog.deleteLater()
    window.deleteLater()
    app.processEvents()


def test_claude_builder_is_visible_but_blocked_in_production(tmp_path: Path) -> None:
    app = _app()
    pack = _exported_pack(tmp_path)
    with patch(
        "relic_auditor.dashboard.supervisor_dialog.shutil.which",
        return_value="C:/tools/claude.exe",
    ):
        dialog = AssistedBuildDialog(PREMIUM, pack, tmp_path / "sessions")
        dialog.stack.setCurrentIndex(2)
        dialog.builder_combo.setCurrentIndex(1)
        app.processEvents()
        assert dialog.builder_status.text() == "PREVIEW BLOCKED"
        assert "not an OS isolation boundary" in dialog.builder_message.text()
        assert not dialog.next_button.isEnabled()
        assert not dialog.cancel_button.isEnabled()
        dialog.deleteLater()
        app.processEvents()
