from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog

from relic_auditor.audit import audit_estate
from relic_auditor.build_packs import BuildPackService
from relic_auditor.dashboard.build_pack_dialog import BuildPackDialog
from relic_auditor.dashboard.qt_app import RelicWindow
from relic_auditor.product_discovery.entitlements import (
    FREE_ENTITLEMENT,
    entitlement_for_testing,
)


def _app():
    return QApplication.instance() or QApplication([])


def _pack(tmp_path: Path, *, premium: bool = True):
    root = tmp_path / "estate"
    (root / "src").mkdir(parents=True)
    (root / "LICENSE").write_text("MIT License", encoding="utf-8")
    (root / "src" / "core.py").write_text(
        "def core():\n    return True\n", encoding="utf-8"
    )
    audit = audit_estate(root)
    record = next(record for record in audit.files if record.path == "src/core.py")
    opportunity = {
        "opportunity_id": "opp_ui",
        "title": "Prepared product",
        "summary": "A bounded prepared product.",
        "evidence": ["ev_a", "ev_b"],
        "evidence_score": 80,
        "technical_verification_status": "moderate",
        "reusable_assets": [
            {"path": record.path, "sha256": record.sha256, "evidence": ["ev_a"]}
        ],
        "missing_components": ["Integration test"],
    }
    entitlement = entitlement_for_testing("premium") if premium else FREE_ENTITLEMENT
    service = BuildPackService(entitlement)
    if not premium:
        return root, service, None
    pack = service.prepare(
        {"opportunities": [opportunity]}, "opp_ui", audit=audit, source_root=root
    )
    return root, service, pack


def test_01_free_user_cannot_construct_premium_dialog(tmp_path: Path):
    app = _app()
    root, premium_service, pack = _pack(tmp_path)
    free = BuildPackService(FREE_ENTITLEMENT)
    with pytest.raises(PermissionError):
        BuildPackDialog(free, pack, tmp_path / "exports")
    app.processEvents()


def test_02_wizard_has_five_ordered_review_steps(tmp_path: Path):
    app = _app()
    _, service, pack = _pack(tmp_path)
    dialog = BuildPackDialog(service, pack, tmp_path / "exports")
    assert dialog.stack.count() == 5
    assert dialog.step_label.text().startswith("Step 1 of 5")
    for index in range(4):
        dialog.next_step()
        assert dialog.stack.currentIndex() == index + 1
    dialog.deleteLater()
    app.processEvents()


def test_03_keyboard_controls_and_screen_reader_labels(tmp_path: Path):
    app = _app()
    _, service, pack = _pack(tmp_path)
    dialog = BuildPackDialog(service, pack, tmp_path / "exports")
    assert dialog.accessibleName()
    assert dialog.cancel_button.accessibleName()
    assert dialog.back_button.accessibleName()
    assert dialog.next_button.accessibleName()
    dialog.next_step()
    dialog.previous_step()
    assert dialog.stack.currentIndex() == 0
    dialog.deleteLater()
    app.processEvents()


def test_04_asset_review_is_exact_and_unselected_by_default(tmp_path: Path):
    app = _app()
    _, service, pack = _pack(tmp_path)
    dialog = BuildPackDialog(service, pack, tmp_path / "exports")
    assert dialog.asset_list.count() == 1
    item = dialog.asset_list.item(0)
    assert item.data(Qt.ItemDataRole.UserRole) == "src/core.py"
    assert item.checkState() == Qt.CheckState.Unchecked
    assert dialog.selected_assets() == ()
    dialog.deleteLater()
    app.processEvents()


def test_05_cancel_leaves_no_export(tmp_path: Path):
    app = _app()
    _, service, pack = _pack(tmp_path)
    output = tmp_path / "exports"
    dialog = BuildPackDialog(service, pack, output)
    dialog.reject()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert not output.exists()
    dialog.deleteLater()
    app.processEvents()


def test_06_focused_flow_replaces_three_tabs_and_keeps_evidence_collapsed(tmp_path: Path):
    app = _app()
    status = {"ready": False, "executable_found": False, "logged_in": False}
    with patch("relic_auditor.dashboard.qt_app.claude_max_status", return_value=status):
        window = RelicWindow()
    assert not hasattr(window, "primary_tabs")
    assert window.flow_stack.count() == 7
    assert window.flow_stack.currentWidget() is window.scan_page
    assert window.shell_stack.currentWidget() is window.product_shell
    assert not window.prepare_product_button.isVisible()
    assert not window.tabs.isVisible()
    window.close()
    app.processEvents()
