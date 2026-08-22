from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication, QLabel

from relic_auditor.audit import audit_estate
from relic_auditor.build_packs import BuildPackService
from relic_auditor.dashboard.components import PrimaryButton
from relic_auditor.dashboard.core import DashboardBundle, DashboardOptions
from relic_auditor.dashboard.flow import (
    FlowController,
    FlowState,
    focused_answer,
    product_friendly_title,
)
from relic_auditor.dashboard.qt_app import RelicWindow
from relic_auditor.product_discovery.entitlements import (
    FREE_ENTITLEMENT,
    entitlement_for_testing,
)
from relic_auditor.product_discovery.schemas import DiscoveryResult

PREMIUM = entitlement_for_testing("premium")
PRO = entitlement_for_testing("pro")


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _bundle(
    tmp_path: Path, entitlement=PREMIUM
) -> DashboardBundle:
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
        entitlement=entitlement,
    )


def _ready_window(
    app: QApplication, bundle: DashboardBundle, entitlement
) -> RelicWindow:
    window = RelicWindow(entitlement=entitlement)
    window.target_selector.set_path(str(bundle.audit.target))
    window.bundle = bundle
    bundle.entitlement = entitlement
    window._load_bundle(bundle)
    window._load_plain_english_results(bundle)
    window._set_flow_state(FlowState.SCANNING)
    window._set_flow_state(FlowState.ANSWER_READY)
    window.show()
    app.processEvents()
    return window


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
    flow.transition(FlowState.OPPORTUNITY_CHOOSER)
    flow.transition(FlowState.OPPORTUNITY_SELECTED)
    flow.transition(FlowState.PREPARE_PRODUCT)
    flow.transition(FlowState.BUILD_PACK_GATE)
    flow.transition(FlowState.PREPARE_PRODUCT)
    flow.transition(FlowState.BUILD_PACK_READY)
    flow.transition(FlowState.BUILD_SESSION_ACTIVE)
    assert flow.state is FlowState.BUILD_SESSION_ACTIVE


def test_supported_technical_opportunity_name_gets_a_plain_product_title() -> None:
    assert (
        product_friendly_title("Traceable compliance gap assessment")
        == "Compliance Gap Assessment Platform"
    )


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
        assert "reusable asset" in window.answer_supporting_summary.text()
        assert "need attention" in window.answer_supporting_summary.text()
        assert "Prepare" in window.answer_recommendation_label.text()
        assert window.prepare_product_button.text() == "PREPARE THIS PRODUCT"
        assert not window.opportunity_page.isVisible()
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
        assert window.flow.state is FlowState.PREPARE_PRODUCT
        assert window.create_build_pack_button.text() == "CREATE BUILD PACK"
        assert [button.text() for button in _visible_primary_actions(window)] == [
            "CREATE BUILD PACK"
        ]

        window.open_history()
        assert window.flow.state is FlowState.PREPARE_PRODUCT
        assert window.shell_stack.currentWidget() is window.history_shell
        assert _visible_primary_actions(window) == []
        assert not hasattr(window, "workflow_step_badge")

        window.close_secondary_surface()
        window.open_settings()
        assert window.flow.state is FlowState.PREPARE_PRODUCT
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


def test_other_opportunities_is_a_ranked_chooser_with_contextual_evidence(
    app: QApplication, tmp_path: Path
) -> None:
    bundle = _bundle(tmp_path)
    window = _ready_window(app, bundle, PREMIUM)
    try:
        window.open_opportunity_chooser()
        app.processEvents()
        assert window.flow.state is FlowState.OPPORTUNITY_CHOOSER
        assert window.shell_stack.currentWidget() is window.product_shell
        assert window.flow_stack.currentWidget() is window.opportunity_page
        assert window.shell_stack.currentWidget() is not window.technical_shell
        assert len(window.opportunity_card_widgets) == 2
        assert len(window.opportunity_select_buttons) == 2
        assert len(window.opportunity_why_buttons) == 2
        card_text = [
            " ".join(label.text() for label in card.findChildren(QLabel))
            for card in window.opportunity_card_widgets
        ]
        assert "Unify the existing application surface" in card_text[0]
        assert "Reusable internal platform layer" in card_text[1]

        window.open_opportunity_evidence("opp_secondary")
        app.processEvents()
        assert window.shell_stack.currentWidget() is window.technical_shell
        assert "Reusable internal platform layer" in window.technical_context.text()
        assert window.back_to_product_button.text() == "Back to Opportunity"
        window.close_technical_details()
        assert window.flow.state is FlowState.OPPORTUNITY_CHOOSER
        assert window.flow_stack.currentWidget() is window.opportunity_page

        window.select_opportunity("opp_secondary")
        app.processEvents()
        assert window.flow.state is FlowState.OPPORTUNITY_SELECTED
        assert window.flow_stack.currentWidget() is window.answer_page
        assert "Reusable internal platform layer" in (
            window.best_opportunity_card.body_label.text()
        )
        assert "PREPARE THIS PRODUCT" == window.prepare_product_button.text()
        window.prepare_leading_product()
        assert window.flow.state is FlowState.PREPARE_PRODUCT
        assert "Reusable internal platform layer" in window.prepare_heading.text()
    finally:
        window.close()


@pytest.mark.parametrize(
    ("entitlement", "tier"),
    (
        (FREE_ENTITLEMENT, "Free"),
        (PRO, "Pro"),
        (PREMIUM, "Premium"),
    ),
)
def test_prepare_is_available_on_every_tier_and_explains_the_product(
    app: QApplication, tmp_path: Path, entitlement, tier: str
) -> None:
    bundle = _bundle(tmp_path, entitlement)
    window = _ready_window(app, bundle, entitlement)
    try:
        assert window.prepare_product_button.isEnabled(), tier
        assert _visible_primary_actions(window) == [window.prepare_product_button]
        window.prepare_leading_product()
        app.processEvents()
        assert window.flow.state is FlowState.PREPARE_PRODUCT
        assert window.flow_stack.currentWidget() is window.prepare_page
        assert "Consolidated full-stack platform" in window.prepare_heading.text()
        assert "Unify the existing application surface" in (
            window.prepare_product_card.body_label.text()
        )
        assert "reusable asset" in window.prepare_reuse_card.body_label.text()
        assert "Integration tests" in window.prepare_missing_card.body_label.text()
        assert "focused workflow" in window.prepare_mvp_card.body_label.text()
        assert _visible_primary_actions(window) == [window.create_build_pack_button]
    finally:
        window.close()


@pytest.mark.parametrize("entitlement", (FREE_ENTITLEMENT, PRO), ids=("free", "pro"))
def test_create_build_pack_is_the_gate_and_domain_enforcement_cannot_be_bypassed(
    app: QApplication, tmp_path: Path, entitlement
) -> None:
    bundle = _bundle(tmp_path, entitlement)
    window = _ready_window(app, bundle, entitlement)
    try:
        window.prepare_leading_product()
        window.create_build_pack()
        app.processEvents()
        assert window.flow.state is FlowState.BUILD_PACK_GATE
        assert window.flow_stack.currentWidget() is window.build_pack_gate_page
        assert "requires Premium" in window.build_pack_gate_message.text()
        assert "entitlement" not in window.build_pack_gate_message.text().casefold()
        assert window._prepared_build_pack is None
        assert _visible_primary_actions(window) == [window.view_premium_button]

        # Moving the visible page or enabling a control is presentation-only.
        window.flow_stack.setCurrentWidget(window.prepare_page)
        window.create_build_pack_button.setEnabled(True)
        window.create_build_pack()
        assert window.flow.state is FlowState.BUILD_PACK_GATE
        assert window.flow_stack.currentWidget() is window.build_pack_gate_page

        with pytest.raises(PermissionError):
            BuildPackService(entitlement).prepare(
                bundle.discovery,
                "opp_focused_flow",
                audit=bundle.audit,
                source_root=bundle.audit.target,
            )
    finally:
        window.close()


def test_premium_create_reaches_canonical_pack_for_selected_opportunity(
    app: QApplication, tmp_path: Path, monkeypatch
) -> None:
    bundle = _bundle(tmp_path, PREMIUM)
    window = _ready_window(app, bundle, PREMIUM)
    captured: dict[str, object] = {}

    class ReviewWasOpened:
        def __init__(self, service, pack, output, parent) -> None:
            captured["service"] = service
            captured["pack"] = pack
            captured["output"] = output
            captured["parent"] = parent

        def exec(self) -> int:
            return 0

    monkeypatch.setattr(
        "relic_auditor.dashboard.qt_app.BuildPackDialog", ReviewWasOpened
    )
    try:
        window.open_opportunity_chooser()
        window.select_opportunity("opp_secondary")
        window.prepare_leading_product()
        window.create_build_pack()
        pack = captured["pack"]
        assert pack.content["opportunity"]["opportunity_id"] == "opp_secondary"
        assert window.flow.state is FlowState.PREPARE_PRODUCT
    finally:
        window.close()


def test_technical_evidence_is_proof_and_settings_owns_configuration(
    app: QApplication, tmp_path: Path
) -> None:
    bundle = _bundle(tmp_path)
    window = _ready_window(app, bundle, PREMIUM)
    try:
        window.open_selected_opportunity_evidence()
        app.processEvents()
        assert window.shell_stack.currentWidget() is window.technical_shell
        assert not window.technical_shell.isAncestorOf(window.mode)
        assert not window.technical_shell.isAncestorOf(window.include_hidden)
        assert not window.technical_shell.isAncestorOf(window.use_llm)
        assert not window.technical_shell.isAncestorOf(window.llm_provider)
        assert not window.technical_shell.isAncestorOf(window.provider_card)
        evidence_tabs = {
            window.tabs.tabText(index).split(" (", 1)[0]
            for index in range(window.tabs.count())
        }
        assert {
            "Evidence Summary",
            "System Map",
            "Technical Truth",
            "Reasoning",
            "Files",
        } <= evidence_tabs
        assert window.tabs.isVisible()
        window.close_technical_details()
        assert window.flow_stack.currentWidget() is window.answer_page

        completed_bundle = window.bundle
        completed_rows = window.files.row_count()
        window.open_settings()
        assert window.settings_tabs.tabText(0) == "Scan"
        assert window.settings_tabs.tabText(1) == "Reasoning"
        assert window.settings_scan_tab.isAncestorOf(window.mode)
        assert window.settings_reasoning_tab.isAncestorOf(window.use_llm)
        assert window.settings_reasoning_tab.isAncestorOf(window.provider_card)
        window.mode.setCurrentIndex(window.mode.findData("quick"))
        window.include_hidden.setChecked(True)
        assert window.bundle is completed_bundle
        assert window.files.row_count() == completed_rows
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
        window.settings_tabs.setCurrentWidget(window.settings_tabs.widget(2))
        window.toggle_update_diagnostics()
        assert window.update_diagnostic_label.isVisible()
    finally:
        window.close()
