from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication

from relic_auditor.audit import audit_estate
from relic_auditor.dashboard.components import PrimaryButton
from relic_auditor.dashboard.core import DashboardBundle, DashboardOptions
from relic_auditor.dashboard.flow import (
    FlowController,
    FlowState,
    focused_answer,
)
from relic_auditor.dashboard.qt_app import RelicWindow
from relic_auditor.product_discovery.entitlements import (
    entitlement_for_testing,
)
from relic_auditor.product_discovery.schemas import DiscoveryResult

PREMIUM = entitlement_for_testing("premium")


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _bundle(tmp_path: Path) -> DashboardBundle:
    estate = tmp_path / "Powerhouse Platform"
    estate.mkdir()
    (estate / "app.py").write_text(
        "def create_product():\n    return 'ready'\n", encoding="utf-8"
    )
    audit = audit_estate(estate)
    opportunity = {
        "opportunity_id": "opp_focused_flow",
        "title": "Consolidated full-stack platform",
        "summary": "Unify the existing application surface into one focused product.",
        "evidence": ["ev_app", "ev_route"],
        "evidence_score": 84,
        "evidence_strength": "strong",
        "technical_verification_status": "moderate",
        "build_pack_readiness": "eligible",
        "reusable_assets": [
            {
                "path": "app.py",
                "sha256": audit.files[0].sha256,
                "evidence": ["ev_app"],
            }
        ],
        "missing_components": ["Integration tests", "Production authentication"],
        "mvp_scope": "One focused workflow backed by the existing application core.",
    }
    discovery = DiscoveryResult(
        intent={},
        capabilities=[],
        opportunities=[
            opportunity,
            {
                **opportunity,
                "opportunity_id": "opp_secondary",
                "title": "Reusable internal platform layer",
                "evidence_strength": "medium",
            },
        ],
        evidence_index=[],
        extraction_plans=[],
        market_validation={"status": "not_performed"},
        project_families=[],
    )
    return DashboardBundle(
        audit=audit,
        options=DashboardOptions(product_discovery=True),
        discovery=discovery,
        entitlement=PREMIUM,
    )


def _visible_primary_actions(window: RelicWindow) -> list[PrimaryButton]:
    return [
        button
        for button in window.findChildren(PrimaryButton)
        if button.isVisibleTo(window)
    ]


def test_state_model_rejects_skipped_governance_states() -> None:
    flow = FlowController()
    with pytest.raises(ValueError, match="invalid focused-flow transition"):
        flow.transition(FlowState.BUILD_SESSION_ACTIVE)
    flow.transition(FlowState.TARGET_SELECTED)
    flow.transition(FlowState.SCANNING)
    flow.transition(FlowState.ANSWER_READY)
    flow.transition(FlowState.PREPARING_PRODUCT)
    flow.transition(FlowState.BUILD_PACK_READY)
    flow.transition(FlowState.BUILD_SESSION_ACTIVE)
    assert flow.state is FlowState.BUILD_SESSION_ACTIVE


def test_scan_is_focused_and_advanced_controls_are_hidden(app: QApplication) -> None:
    window = RelicWindow()
    window.show()
    app.processEvents()
    try:
        assert window.flow.state is FlowState.NO_TARGET
        assert window.flow_stack.currentWidget() is window.scan_page
        assert window.run_button.text() == "SCAN THIS FOLDER"
        assert not window.mode.isVisible()
        assert not window.include_hidden.isVisible()
        assert not window.provider_card.isVisible()
        assert [button.text() for button in _visible_primary_actions(window)] == [
            "SCAN THIS FOLDER"
        ]
    finally:
        window.close()


def test_completed_scan_transitions_to_decision_first_answer(
    app: QApplication, tmp_path: Path, monkeypatch
) -> None:
    bundle = _bundle(tmp_path)
    window = RelicWindow(entitlement=PREMIUM)
    window.show()
    window.target_selector.set_path(str(bundle.audit.target))
    window._set_flow_state(FlowState.SCANNING)
    monkeypatch.setattr(window, "_auto_export_reports", lambda _bundle: None)
    monkeypatch.setattr(window, "refresh_report_history", lambda: None)
    window._scan_complete(bundle)
    app.processEvents()
    try:
        answer = focused_answer(bundle)
        assert window.flow.state is FlowState.ANSWER_READY
        assert window.flow_stack.currentWidget() is window.answer_page
        assert window.answer_conclusion.text() == answer["conclusion"]
        assert "Consolidated full-stack platform" in window.best_opportunity_card.body_label.text()
        assert "reusable asset" in window.found_card.body_label.text()
        assert "need attention" in window.risk_card.body_label.text()
        assert "Prepare" in window.next_card.body_label.text()
        assert window.prepare_product_button.text() == "PREPARE THIS PRODUCT"
        assert window.other_opportunities_list.isVisible() is False
        assert [button.text() for button in _visible_primary_actions(window)] == [
            "PREPARE THIS PRODUCT"
        ]
    finally:
        window.close()


def test_prepare_history_settings_and_evidence_preserve_current_flow(
    app: QApplication, tmp_path: Path
) -> None:
    bundle = _bundle(tmp_path)
    window = RelicWindow(entitlement=PREMIUM)
    window.bundle = bundle
    window._load_bundle(bundle)
    window._load_plain_english_results(bundle)
    window.target_selector.set_path(str(bundle.audit.target))
    window._set_flow_state(FlowState.SCANNING)
    window._set_flow_state(FlowState.ANSWER_READY)
    window.show()
    window.prepare_leading_product()
    app.processEvents()
    try:
        assert window.flow.state is FlowState.PREPARING_PRODUCT
        assert window.create_build_pack_button.text() == "CREATE BUILD PACK"
        assert [button.text() for button in _visible_primary_actions(window)] == [
            "CREATE BUILD PACK"
        ]

        window.open_history()
        assert window.flow.state is FlowState.PREPARING_PRODUCT
        assert window.shell_stack.currentWidget() is window.history_shell
        assert _visible_primary_actions(window) == []
        assert not hasattr(window, "workflow_step_badge")

        window.close_secondary_surface()
        window.open_settings()
        assert window.flow.state is FlowState.PREPARING_PRODUCT
        assert window.shell_stack.currentWidget() is window.settings_shell

        window.open_technical_details()
        assert window.tabs.tabText(0) == "Evidence Summary"
        assert "Powerhouse Platform" in window.technical_context.text()
        window.close_technical_details()
        assert window.shell_stack.currentWidget() is window.settings_shell

        window.close_secondary_surface()
        assert window.flow_stack.currentWidget() is window.prepare_page
    finally:
        window.close()


def test_raw_update_failure_is_only_in_deliberate_diagnostics(
    app: QApplication, monkeypatch
) -> None:
    window = RelicWindow()
    window.show()
    app.processEvents()
    captured: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "relic_auditor.dashboard.qt_app.QMessageBox.warning",
        lambda _parent, title, body: captured.append((title, body)),
    )
    window._update_check_manual = True
    raw = "UpdateManifestError: HTTP Error 401 Unauthorized"
    window._update_check_failed(raw)
    try:
        assert captured
        assert raw not in captured[0][1]
        assert "Automatic updates are not available" in captured[0][1]
        assert window.update_diagnostic_label.text() == raw
        assert not window.update_diagnostic_label.isVisible()
        window.open_settings()
        window.settings_tabs.setCurrentIndex(1)
        window.toggle_update_diagnostics()
        assert window.update_diagnostic_label.isVisible()
    finally:
        window.close()
