"""Relic Auditor Evidence Console.

The desktop dashboard. Layout rules that must hold everywhere in this file:

- No fixed pixel height on anything that renders text. Heights come from font
  metrics (see :func:`relic_auditor.dashboard.theme.control_height`) so
  Windows display scaling from 100% to 200% grows controls instead of
  clipping them.
- Any region whose content can exceed the viewport lives in a scroll area.
- Colours, spacing, radii, and type come from
  :mod:`relic_auditor.dashboard.theme`. No raw style strings here.
- Progress is indeterminate whenever a true percentage is unknown; a
  percentage is never invented.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import (
    QObject,
    QStandardPaths,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QCloseEvent, QDesktopServices, QFontMetrics
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..build_packs import BuildPackService
from ..licensing import load_cached_entitlement
from ..llm.claude_code import (
    DEFAULT_EFFORT,
    MODEL_ALIASES,
    SUPPORTED_EFFORTS,
    ClaudeCodeError,
)
from ..llm.health import load_provider_health, save_provider_health
from ..product_discovery.entitlements import Entitlement, ProductCapability
from ..updater import (
    DEFAULT_UPDATE_MANIFEST_URL,
    PreparedUpdate,
    UpdateManifest,
    fetch_update_manifest,
    launch_prepared_update,
    prepare_update,
    save_update_check_state,
    should_check_automatically,
)
from .build_pack_dialog import BuildPackDialog
from .components import (
    ElidedLabel,
    EmptyState,
    EvidenceCard,
    FindingsTable,
    MetricCard,
    PathSelector,
    PrimaryButton,
    ProviderStatusCard,
    RelicPanel,
    ScanProgressPanel,
    SecondaryButton,
    StatusBadge,
    hairline,
    section_label,
)
from .core import (
    DEFAULT_CLAUDE_MAX_PROFILE,
    DashboardBundle,
    DashboardOptions,
    automatic_report_directory,
    claude_max_status,
    default_reports_root,
    ensure_claude_max_profile,
    export_dashboard_bundle,
    launch_claude_login,
    list_report_history,
    run_dashboard_audit,
)
from .flow import FlowController, FlowState, focused_answer, product_friendly_title
from .license_dialog import LicenseDialog
from .supervisor_dialog import AssistedBuildDialog
from .theme import BREAKPOINTS, SPACING, control_height, stylesheet
from .update_dialog import UpdateDialog
from .widgets import (
    ArchitectureView,
    CandidateTable,
    OverviewWidget,
    TechnicalTruthWidget,
    public_record,
)


class ScanWorker(QObject):
    """Runs the read-only audit off the UI thread."""

    progress = Signal(int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self, target: Path, options: DashboardOptions, entitlement: Entitlement
    ) -> None:
        super().__init__()
        self.target = target
        self.options = options
        self.entitlement = entitlement
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation.

        The scan only ever reads, so stopping early leaves the target exactly
        as it was; there is nothing to roll back.
        """

        self._cancelled = True

    @Slot()
    def run(self) -> None:
        def report(value: int, message: str) -> None:
            if self._cancelled:
                raise _ScanCancelled()
            self.progress.emit(value, message)

        try:
            bundle = run_dashboard_audit(
                self.target,
                self.options,
                report,
                entitlement=self.entitlement,
            )
        except _ScanCancelled:
            self.failed.emit("__cancelled__")
            return
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(bundle)


class _ScanCancelled(Exception):
    """Internal signal that the user asked to stop."""


class UpdateCheckWorker(QObject):
    """Fetch and validate the small stable-channel manifest off the UI thread."""

    finished = Signal(object)
    failed = Signal(str)

    @Slot()
    def run(self) -> None:
        try:
            manifest = fetch_update_manifest(DEFAULT_UPDATE_MANIFEST_URL)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(manifest)


class UpdateDownloadWorker(QObject):
    """Download and publisher-verify an update without freezing the dashboard."""

    progress = Signal(int, int)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, manifest: UpdateManifest) -> None:
        super().__init__()
        self.manifest = manifest

    @Slot()
    def run(self) -> None:
        try:
            prepared = prepare_update(
                self.manifest,
                progress=lambda received, total: self.progress.emit(received, total),
            )
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(prepared)


class RelicWindow(QMainWindow):
    def __init__(
        self,
        initial_target: Path | None = None,
        *,
        entitlement: Entitlement | None = None,
    ) -> None:
        super().__init__()
        self.bundle: DashboardBundle | None = None
        self.entitlement = entitlement or load_cached_entitlement()
        self.report_directory: Path | None = None
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        self._update_check_thread: QThread | None = None
        self._update_check_worker: UpdateCheckWorker | None = None
        self._update_download_thread: QThread | None = None
        self._update_download_worker: UpdateDownloadWorker | None = None
        self._update_check_manual = False
        self._available_update: UpdateManifest | None = None
        self._prepared_update: PreparedUpdate | None = None
        self._update_dialog: UpdateDialog | None = None
        self._close_when_done = False
        self._scan_started_at: float | None = None
        self._provider_configured = False
        self.flow = FlowController()
        self._technical_origin: QWidget | None = None
        self._technical_opportunity_id: str | None = None
        self._selected_opportunity_id: str | None = None
        self._opportunity_was_selected = False
        self._all_opportunity_rows: list[dict[str, object]] = []
        self._prepared_build_pack = None
        self._exported_build_pack = None
        self._build_pack_service: BuildPackService | None = None
        self._last_update_diagnostic = "No update diagnostic has been recorded."
        documents = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
        self.reports_root = default_reports_root(
            Path(documents) if documents else Path.home() / "Documents"
        )
        self._history_entries = []

        self.setWindowTitle(f"Relic Auditor {__version__}")
        self.resize(1380, 900)
        self.setMinimumSize(BREAKPOINTS.minimum_width, BREAKPOINTS.minimum_height)
        self.setStyleSheet(stylesheet())

        self._build_controls(initial_target)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(hairline())

        self.shell_stack = QStackedWidget()
        self.product_shell = self._build_product_shell()
        self.history_shell = self._build_history_shell()
        self.settings_shell = self._build_settings_shell()
        self.technical_shell = self._build_technical_shell()
        self.shell_stack.addWidget(self.product_shell)
        self.shell_stack.addWidget(self.history_shell)
        self.shell_stack.addWidget(self.settings_shell)
        self.shell_stack.addWidget(self.technical_shell)
        self.shell_stack.setCurrentWidget(self.product_shell)
        root.addWidget(self.shell_stack, 1)
        self.setCentralWidget(central)

        # The status bar hosts its own eliding label rather than showMessage():
        # a plain message was cropping descenders against the window edge, and
        # a long message would have widened the window instead of eliding.
        status = QStatusBar()
        status.setSizeGripEnabled(False)
        self.status_message = ElidedLabel(
            "Ready"
        )
        self.status_message.setObjectName("statusMessage")
        metrics = QFontMetrics(self.status_message.font())
        # Font height plus a little padding, computed directly rather than via
        # control_height: a status line is not a click target, so the 28px
        # touch-target floor would only waste vertical space. This still grows
        # with the font from 100% through 200% Windows scaling, and the extra
        # descent allowance keeps glyph tails off the window edge.
        line_height = metrics.height() + metrics.descent() + SPACING.xs
        self.status_message.setMinimumHeight(line_height)
        status.addWidget(self.status_message, 1)
        status.setMinimumHeight(line_height + SPACING.xs)
        status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStatusBar(status)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)

        self._update_llm_controls()
        self._refresh_provider(initial=True)
        self.refresh_report_history()
        self._set_flow_state(
            FlowState.TARGET_SELECTED if initial_target is not None else FlowState.NO_TARGET,
            new_workflow=True,
        )
        if initial_target is not None:
            QTimer.singleShot(150, self.start_scan)
        if getattr(sys, "frozen", False) and should_check_automatically():
            QTimer.singleShot(2500, self._auto_check_for_updates)

    # -- construction -----------------------------------------------------

    def _build_controls(self, initial_target: Path | None) -> None:
        self.target_selector = PathSelector("Folder to scan", "Choose a project folder")
        if initial_target is not None:
            self.target_selector.set_path(str(initial_target.expanduser().resolve()))
        self.target_selector.path_changed.connect(self._target_changed)

        self.output_selector = PathSelector(
            "Report output", "Defaults to <target>-relic-report, outside the target"
        )

        self.mode = QComboBox()
        self.mode.addItem("Complete appraisal (recommended)", "full")
        self.mode.addItem("Technical Truth", "truth")
        self.mode.addItem("Reusable Assets", "acquisition")
        self.mode.addItem("Quick inventory", "quick")
        self.mode.addItem("Product Resurrection", "resurrection")
        self.mode.setAccessibleName("Analysis mode")
        self.mode.setMinimumHeight(control_height(QFontMetrics(self.mode.font())))

        self.include_hidden = QCheckBox("Include hidden files")
        self.include_hidden.setAccessibleName("Include hidden files")

        self.use_llm = QCheckBox("Enable advisory reasoning")
        self.use_llm.setAccessibleName("Enable advisory reasoning")
        self.use_llm.setToolTip(
            "Sends only bounded, secret-redacted evidence. Deterministic "
            "reports are produced either way."
        )
        self.use_llm.toggled.connect(self._update_llm_controls)

        self.llm_provider = QComboBox()
        # Labels stay short enough to render fully in the sidebar; the billing
        # model is spelled out in the provider card rather than crammed into
        # the control, which is what previously forced a clipped combo.
        self.llm_provider.addItem("Claude Code / Claude Max", "claude-max")
        self.llm_provider.addItem("Configured profile", "profile")
        self.llm_provider.setItemData(
            0,
            "Reason through the local Claude Code CLI on your Claude.ai "
            "subscription session (not Anthropic API-key billing).",
            Qt.ItemDataRole.ToolTipRole,
        )
        self.llm_provider.setItemData(
            1,
            "Use a configured API-key or OAuth profile (metered API billing).",
            Qt.ItemDataRole.ToolTipRole,
        )
        self.llm_provider.setAccessibleName("Reasoning provider")
        self.llm_provider.setMinimumHeight(
            control_height(QFontMetrics(self.llm_provider.font()))
        )
        # Wide enough for the longest entry, so the name is never clipped.
        self.llm_provider.setMinimumWidth(
            QFontMetrics(self.llm_provider.font()).horizontalAdvance(
                "Claude Code / Claude Max"
            )
            + SPACING.xxl
        )
        self.llm_provider.currentIndexChanged.connect(self._update_llm_controls)

        self.llm_profile = QLineEdit()
        self.llm_profile.setPlaceholderText("Configured profile name")
        self.llm_profile.setAccessibleName("LLM profile name")
        self.llm_profile.setMinimumHeight(
            control_height(QFontMetrics(self.llm_profile.font()))
        )

        self.claude_model = QComboBox()
        for alias in MODEL_ALIASES:
            self.claude_model.addItem(alias, alias)
        self.claude_model.setAccessibleName("Claude model alias")
        self.claude_model.setMinimumHeight(
            control_height(QFontMetrics(self.claude_model.font()))
        )
        self.claude_model.currentIndexChanged.connect(
            self._update_reasoning_speed_note
        )

        self.claude_effort = QComboBox()
        for effort in SUPPORTED_EFFORTS:
            self.claude_effort.addItem(effort, effort)
        self.claude_effort.setCurrentText(DEFAULT_EFFORT)
        self.claude_effort.setAccessibleName("Reasoning effort")
        self.claude_effort.setMinimumHeight(
            control_height(QFontMetrics(self.claude_effort.font()))
        )
        self.claude_effort.currentIndexChanged.connect(
            self._update_reasoning_speed_note
        )

        self.run_button = PrimaryButton("SCAN THIS FOLDER")
        self.run_button.setAccessibleName("Scan this folder")
        self.run_button.clicked.connect(self.start_scan)
        self.run_button.setEnabled(bool(initial_target))

        self.export_button = SecondaryButton("Export reports")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_reports)
        self.open_button = SecondaryButton("Open report folder")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_report_folder)

        self.provider_badge = StatusBadge("idle", "PROVIDER: NOT CHECKED")

        self.provider_card = ProviderStatusCard()
        self.provider_card.check_requested.connect(self._refresh_provider)
        self.provider_card.login_requested.connect(self.open_claude_login)

        self.scan_panel = ScanProgressPanel()
        self.scan_panel.cancel_requested.connect(self.cancel_scan)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("headerBar")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(SPACING.xl, SPACING.md, SPACING.xl, SPACING.md)
        layout.setSpacing(SPACING.lg)

        identity = QVBoxLayout()
        identity.setSpacing(0)
        brand = QLabel("RELIC AUDITOR")
        brand.setObjectName("brandMark")
        identity.addWidget(brand)
        layout.addLayout(identity)
        layout.addStretch(1)

        self.trust_badge = StatusBadge("active", "SCAN TARGET · READ-ONLY")
        self.trust_badge.setToolTip(
            "Audits only read and classify the selected target. Assisted builds, "
            "when explicitly approved, run later in a separate managed workspace."
        )
        self.update_button = SecondaryButton("Check updates")
        self.update_button.setAccessibleName("Check for Relic Auditor updates")
        self.update_button.clicked.connect(self.check_for_updates)
        self.version_label = QLabel(f"v{__version__}")
        self.version_label.setObjectName("dimLabel")

        self.plan_badge = StatusBadge(
            "ready" if self.entitlement.license_id else "idle",
            f"PLAN: {self.entitlement.tier.value.upper()}",
        )
        self.plan_button = SecondaryButton("Manage plan")
        self.plan_button.setAccessibleName("Manage Relic plan and license")
        self.plan_button.clicked.connect(self.manage_plan)

        self.history_button = SecondaryButton("History")
        self.history_button.setAccessibleName("Open scan history")
        self.history_button.clicked.connect(self.open_history)
        self.settings_button = SecondaryButton("Settings")
        self.settings_button.setAccessibleName("Open Relic settings")
        self.settings_button.clicked.connect(self.open_settings)

        layout.addWidget(self.history_button)
        layout.addWidget(self.settings_button)
        layout.addWidget(self.version_label)
        return header

    def _build_product_shell(self) -> QWidget:
        shell = QWidget()
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(SPACING.xl, SPACING.lg, SPACING.xl, SPACING.xl)
        layout.setSpacing(SPACING.lg)

        self.flow_stack = QStackedWidget()
        self.scan_page = self._build_scan_page()
        self.scanning_page = self._build_scanning_page()
        self.answer_page = self._build_results_page()
        self.opportunity_page = self._build_opportunity_page()
        self.prepare_page = self._build_prepare_page()
        self.build_pack_gate_page = self._build_build_pack_gate_page()
        self.build_pack_page = self._build_build_pack_page()
        for page in (
            self.scan_page,
            self.scanning_page,
            self.answer_page,
            self.opportunity_page,
            self.prepare_page,
            self.build_pack_gate_page,
            self.build_pack_page,
        ):
            self.flow_stack.addWidget(page)
        layout.addWidget(self.flow_stack, 1)
        return shell

    def _build_scan_page(self) -> QWidget:
        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        column.setSpacing(SPACING.xl)

        intro = RelicPanel(
            "Choose a folder to analyze.",
            "Relic will inspect the software and explain what is valuable and what to do next.",
            emphasis=True,
        )
        intro.add_widget(self.target_selector)
        self.source_reassurance = QLabel("Source remains read-only.")
        self.source_reassurance.setObjectName("dimLabel")
        self.source_reassurance.setAccessibleName(
            "Selected source remains read-only during scanning"
        )
        self.source_reassurance.setVisible(bool(self.target_selector.path()))
        intro.add_widget(self.source_reassurance)
        actions = QHBoxLayout()
        actions.addWidget(self.run_button)
        actions.addStretch(1)
        self.scan_technical_button = SecondaryButton("Options")
        self.scan_technical_button.setAccessibleName("Open advanced scan options")
        self.scan_technical_button.clicked.connect(self.open_scan_settings)
        actions.addWidget(self.scan_technical_button)
        intro.add_layout(actions)
        column.addWidget(intro)
        column.addStretch(1)

        scroller = QScrollArea()
        scroller.setWidget(content)
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.Shape.NoFrame)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return scroller

    def _build_scanning_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        layout.setSpacing(SPACING.xl)
        self.scanning_title = QLabel("Analyzing…")
        self.scanning_title.setObjectName("emptyTitle")
        self.scanning_title.setWordWrap(True)
        self.scanning_title.setAccessibleName("Current scan")
        scanning_note = QLabel(
            "Relic is reading and classifying the selected source. It will open the "
            "answer automatically when the analysis is complete."
        )
        scanning_note.setObjectName("mutedLabel")
        scanning_note.setWordWrap(True)
        layout.addWidget(self.scanning_title)
        layout.addWidget(scanning_note)
        layout.addWidget(self.scan_panel)
        layout.addStretch(1)
        return page

    def _build_results_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        layout.setSpacing(SPACING.lg)

        self.results_empty = EmptyState(
            "No answer yet",
            "Choose a folder and scan it. Relic will explain the strongest evidence-backed path here.",
            marker=EmptyState.EVIDENCE_MARKER,
        )
        layout.addWidget(self.results_empty, 1)

        self.results_content = QWidget()
        results_layout = QVBoxLayout(self.results_content)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(SPACING.md)
        self.answer_conclusion = QLabel("Relic is preparing the answer.")
        self.answer_conclusion.setObjectName("answerConclusion")
        self.answer_conclusion.setWordWrap(True)
        self.answer_conclusion.setAccessibleName("Plain-English appraisal conclusion")
        self.answer_detail = QLabel("")
        self.answer_detail.setObjectName("mutedLabel")
        self.answer_detail.setWordWrap(True)
        results_layout.addWidget(self.answer_conclusion)
        results_layout.addWidget(self.answer_detail)

        self.best_opportunity_card = EvidenceCard("BEST OPPORTUNITY")
        results_layout.addWidget(self.best_opportunity_card)
        self.answer_supporting_summary = QLabel("")
        self.answer_supporting_summary.setObjectName("dimLabel")
        self.answer_supporting_summary.setWordWrap(True)
        self.answer_supporting_summary.setAccessibleName(
            "Supporting reusable asset and attention summary"
        )
        results_layout.addWidget(self.answer_supporting_summary)
        self.answer_recommendation_heading = section_label("RECOMMENDED NEXT MOVE")
        self.answer_recommendation_label = QLabel("")
        self.answer_recommendation_label.setObjectName("mutedLabel")
        self.answer_recommendation_label.setWordWrap(True)
        results_layout.addWidget(self.answer_recommendation_heading)
        results_layout.addWidget(self.answer_recommendation_label)

        actions = QHBoxLayout()
        self.prepare_product_button = PrimaryButton("PREPARE THIS PRODUCT")
        self.prepare_product_button.setAccessibleName(
            "Prepare the leading product as a Build Pack"
        )
        self.prepare_product_button.setVisible(False)
        self.prepare_product_button.clicked.connect(self.prepare_leading_product)
        actions.addWidget(self.prepare_product_button)
        actions.addStretch(1)
        results_layout.addLayout(actions)

        secondary_actions = QHBoxLayout()
        self.other_opportunities_button = SecondaryButton("Other opportunities")
        self.other_opportunities_button.clicked.connect(
            self.toggle_other_opportunities
        )
        self.view_full_report_button = SecondaryButton("Export")
        self.view_full_report_button.setEnabled(False)
        self.view_full_report_button.clicked.connect(self.export_reports)
        self.results_technical_button = SecondaryButton("View technical evidence")
        self.results_technical_button.clicked.connect(
            self.open_selected_opportunity_evidence
        )
        secondary_actions.addWidget(self.other_opportunities_button)
        secondary_actions.addWidget(self.view_full_report_button)
        secondary_actions.addWidget(self.results_technical_button)
        secondary_actions.addStretch(1)
        results_layout.addLayout(secondary_actions)

        results_layout.addStretch(1)

        results_scroll = QScrollArea()
        results_scroll.setWidget(self.results_content)
        results_scroll.setWidgetResizable(True)
        results_scroll.setFrameShape(QFrame.Shape.NoFrame)
        results_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        layout.addWidget(results_scroll, 1)
        self.results_content.setVisible(False)
        return page

    def _build_opportunity_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        outer.setSpacing(SPACING.lg)

        self.opportunity_back_button = SecondaryButton("← Back to Answer")
        self.opportunity_back_button.clicked.connect(self.return_to_answer)
        outer.addWidget(self.opportunity_back_button, 0, Qt.AlignmentFlag.AlignLeft)
        heading = QLabel("Choose an opportunity")
        heading.setObjectName("emptyTitle")
        heading.setWordWrap(True)
        outer.addWidget(heading)
        self.opportunity_count_label = QLabel("")
        self.opportunity_count_label.setObjectName("mutedLabel")
        self.opportunity_count_label.setWordWrap(True)
        outer.addWidget(self.opportunity_count_label)

        self.opportunity_list = QListWidget()
        self.opportunity_list.setAccessibleName("Ranked product opportunities")
        self.opportunity_list.setAccessibleDescription(
            "Choose one product direction. Each row includes rank, evidence, effort, "
            "and reusable-asset count."
        )
        self.opportunity_list.setWordWrap(True)
        self.opportunity_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.opportunity_list.currentItemChanged.connect(
            lambda _current, _previous: self._preview_opportunity_choice()
        )
        self.opportunity_list.itemDoubleClicked.connect(
            lambda _item: self.select_chooser_opportunity()
        )
        outer.addWidget(self.opportunity_list, 1)

        self.opportunity_preview = EvidenceCard("SELECTED OPPORTUNITY")
        self.opportunity_preview.setAccessibleName("Selected opportunity summary")
        outer.addWidget(self.opportunity_preview)

        actions = QHBoxLayout()
        self.choose_opportunity_button = PrimaryButton("SELECT OPPORTUNITY")
        self.choose_opportunity_button.setAccessibleName(
            "Use the highlighted opportunity"
        )
        self.choose_opportunity_button.clicked.connect(
            self.select_chooser_opportunity
        )
        self.chooser_evidence_button = SecondaryButton("View evidence")
        self.chooser_evidence_button.setAccessibleName(
            "View technical evidence for the highlighted opportunity"
        )
        self.chooser_evidence_button.clicked.connect(
            self.open_chooser_opportunity_evidence
        )
        actions.addWidget(self.choose_opportunity_button)
        actions.addWidget(self.chooser_evidence_button)
        actions.addStretch(1)
        outer.addLayout(actions)
        return page

    def _build_prepare_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        layout.setSpacing(SPACING.lg)

        self.prepare_heading = QLabel("Prepare this product")
        self.prepare_heading.setObjectName("emptyTitle")
        self.prepare_heading.setWordWrap(True)
        prompt = QLabel("What exactly are we about to build?")
        prompt.setObjectName("mutedLabel")
        layout.addWidget(self.prepare_heading)
        layout.addWidget(prompt)

        self.prepare_product_card = EvidenceCard("PRODUCT")
        self.prepare_reuse_card = EvidenceCard("WE WILL REUSE")
        self.prepare_missing_card = EvidenceCard("WE STILL NEED")
        self.prepare_mvp_card = EvidenceCard("MVP")
        self.prepare_risks_card = EvidenceCard("IMPORTANT RISKS")
        for card in (
            self.prepare_product_card,
            self.prepare_reuse_card,
            self.prepare_missing_card,
            self.prepare_mvp_card,
            self.prepare_risks_card,
        ):
            layout.addWidget(card)

        primary = QHBoxLayout()
        self.create_build_pack_button = PrimaryButton("CREATE BUILD PACK")
        self.create_build_pack_button.setAccessibleName(
            "Create and review the selected product Build Pack"
        )
        self.create_build_pack_button.clicked.connect(self.create_build_pack)
        primary.addWidget(self.create_build_pack_button)
        primary.addStretch(1)
        layout.addLayout(primary)

        secondary = QHBoxLayout()
        self.change_opportunity_button = SecondaryButton("Change opportunity")
        self.change_opportunity_button.clicked.connect(self.open_opportunity_chooser)
        self.review_assets_button = SecondaryButton("Review reusable assets")
        self.review_assets_button.clicked.connect(self.open_reusable_assets_evidence)
        self.prepare_technical_button = SecondaryButton("View technical evidence")
        self.prepare_technical_button.clicked.connect(
            self.open_selected_opportunity_evidence
        )
        self.prepare_back_button = SecondaryButton("Back to Answer")
        self.prepare_back_button.clicked.connect(self.return_to_answer)
        secondary.addWidget(self.change_opportunity_button)
        secondary.addWidget(self.review_assets_button)
        secondary.addWidget(self.prepare_technical_button)
        secondary.addWidget(self.prepare_back_button)
        secondary.addStretch(1)
        layout.addLayout(secondary)
        layout.addStretch(1)
        return page

    def _build_build_pack_gate_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        layout.setSpacing(SPACING.xl)
        heading = QLabel("Create your Build Pack")
        heading.setObjectName("emptyTitle")
        heading.setWordWrap(True)
        explanation = QLabel(
            "Relic can turn this product direction into an implementation-ready "
            "package containing:"
        )
        explanation.setObjectName("mutedLabel")
        explanation.setWordWrap(True)
        contents = QLabel(
            "• Product brief\n• MVP scope\n• Architecture\n• Implementation plan\n"
            "• Reusable asset manifest\n• Acceptance criteria\n• Builder handoff"
        )
        contents.setObjectName("mutedLabel")
        contents.setWordWrap(True)
        self.build_pack_gate_message = QLabel("Build Pack creation requires Premium.")
        self.build_pack_gate_message.setObjectName("panelTitle")
        self.build_pack_gate_message.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(explanation)
        layout.addWidget(contents)
        layout.addWidget(self.build_pack_gate_message)
        actions = QHBoxLayout()
        self.view_premium_button = PrimaryButton("VIEW PREMIUM")
        self.view_premium_button.clicked.connect(self.manage_plan)
        self.build_pack_gate_back_button = SecondaryButton("Back")
        self.build_pack_gate_back_button.clicked.connect(self.return_to_prepare)
        actions.addWidget(self.view_premium_button)
        actions.addWidget(self.build_pack_gate_back_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch(1)
        return page

    def _build_build_pack_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        layout.setSpacing(SPACING.xl)
        heading = QLabel("Build Pack ready.")
        heading.setObjectName("emptyTitle")
        layout.addWidget(heading)
        self.build_pack_summary = EvidenceCard("RELIC PREPARED")
        self.build_pack_summary.set_body(
            "Product brief\nMVP scope\nArchitecture\nImplementation plan\n"
            "Reusable asset manifest\nAcceptance criteria\nBuilder handoff"
        )
        layout.addWidget(self.build_pack_summary)
        primary = QHBoxLayout()
        self.start_assisted_build_button = PrimaryButton("START ASSISTED BUILD")
        self.start_assisted_build_button.setAccessibleName(
            "Start the approval-gated Assisted Build Supervisor"
        )
        self.start_assisted_build_button.clicked.connect(self.start_assisted_build)
        primary.addWidget(self.start_assisted_build_button)
        primary.addStretch(1)
        layout.addLayout(primary)
        secondary = QHBoxLayout()
        self.open_build_pack_button = SecondaryButton("Open Build Pack")
        self.open_build_pack_button.clicked.connect(self.open_exported_build_pack)
        self.reexport_build_pack_button = SecondaryButton("Export")
        self.reexport_build_pack_button.clicked.connect(self.create_build_pack)
        self.build_pack_technical_button = SecondaryButton("Technical Evidence")
        self.build_pack_technical_button.clicked.connect(self.open_technical_details)
        secondary.addWidget(self.open_build_pack_button)
        secondary.addWidget(self.reexport_build_pack_button)
        secondary.addWidget(self.build_pack_technical_button)
        secondary.addStretch(1)
        layout.addLayout(secondary)
        layout.addStretch(1)
        return page

    def _build_history_shell(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        layout.setSpacing(SPACING.md)

        toolbar = QHBoxLayout()
        back = SecondaryButton("Back")
        back.setAccessibleName("Return to the current workflow")
        back.clicked.connect(self.close_secondary_surface)
        title = QLabel("HISTORY")
        title.setObjectName("emptyTitle")
        toolbar.addWidget(back)
        toolbar.addWidget(title)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.reports_root_label = ElidedLabel(str(self.reports_root))
        self.reports_root_label.setVisible(False)
        self.open_reports_root_button = SecondaryButton("Open Reports folder")
        self.open_reports_root_button.clicked.connect(self.open_reports_root)
        self.open_reports_root_button.setVisible(False)
        self.refresh_reports_button = SecondaryButton("Refresh")
        self.refresh_reports_button.clicked.connect(self.refresh_report_history)
        self.refresh_reports_button.setVisible(False)

        self.reports_empty = EmptyState(
            "No saved scans yet",
            "Complete an audit and its answer will appear here automatically.",
            marker=EmptyState.EVIDENCE_MARKER,
            compact=True,
        )
        layout.addWidget(self.reports_empty)
        self.reports_list = QListWidget()
        self.reports_list.setAccessibleName("Previous scans")
        self.reports_list.itemDoubleClicked.connect(
            lambda _item: self.open_selected_report()
        )
        layout.addWidget(self.reports_list, 1)

        history_actions = QHBoxLayout()
        self.open_selected_report_button = SecondaryButton("Open")
        self.open_selected_report_button.clicked.connect(self.open_selected_report)
        self.open_selected_folder_button = SecondaryButton("Open scan folder")
        self.open_selected_folder_button.clicked.connect(
            self.open_selected_report_folder
        )
        self.open_selected_folder_button.setVisible(False)
        history_actions.addWidget(self.open_selected_report_button)
        history_actions.addStretch(1)
        layout.addLayout(history_actions)
        return page

    def _build_settings_shell(self) -> QWidget:
        shell = QWidget()
        outer = QVBoxLayout(shell)
        outer.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        outer.setSpacing(SPACING.md)
        toolbar = QHBoxLayout()
        back = SecondaryButton("Back")
        back.setAccessibleName("Return to the current workflow")
        back.clicked.connect(self.close_secondary_surface)
        title = QLabel("SETTINGS")
        title.setObjectName("emptyTitle")
        toolbar.addWidget(back)
        toolbar.addWidget(title)
        toolbar.addStretch(1)
        outer.addLayout(toolbar)

        self.settings_tabs = QTabWidget()
        self.settings_tabs.setDocumentMode(True)

        scan = RelicPanel(
            "Scan",
            "These controls change the depth of future audits. Completed evidence is not changed.",
        )
        scan.add_widget(section_label("Analysis mode"))
        scan.add_widget(self.mode)
        scan.add_widget(self.include_hidden)
        self.settings_scan_tab = scan
        self.settings_tabs.addTab(scan, "Scan")

        self.settings_reasoning_tab = self._build_sidebar()
        self.settings_tabs.addTab(self.settings_reasoning_tab, "Reasoning")

        updates = RelicPanel(
            "Updates",
            f"Relic Auditor {__version__} is installed. Automatic updates remain fail-closed unless every trust check passes.",
        )
        self.update_status_label = QLabel("Update status has not been checked in this session.")
        self.update_status_label.setObjectName("mutedLabel")
        self.update_status_label.setWordWrap(True)
        updates.add_widget(self.update_status_label)
        updates.add_widget(self.update_button)
        self.update_diagnostics_button = SecondaryButton("Show technical diagnostics")
        self.update_diagnostics_button.clicked.connect(self.toggle_update_diagnostics)
        updates.add_widget(self.update_diagnostics_button)
        self.update_diagnostic_label = QLabel(self._last_update_diagnostic)
        self.update_diagnostic_label.setObjectName("dimLabel")
        self.update_diagnostic_label.setWordWrap(True)
        self.update_diagnostic_label.setVisible(False)
        updates.add_widget(self.update_diagnostic_label)
        self.settings_tabs.addTab(updates, "Updates")

        plan = RelicPanel(
            "Your plan",
            "Scanning, answers, opportunity selection, and product preparation remain available on every plan. Premium gates Build Pack creation.",
        )
        plan.add_widget(self.plan_badge)
        plan.add_widget(self.plan_button)
        self.settings_tabs.addTab(plan, "Plan")

        storage = RelicPanel(
            "Storage",
            "Completed scans are stored in Relic Auditor's managed report history.",
        )
        storage_path = ElidedLabel(str(self.reports_root))
        storage_path.setToolTip(str(self.reports_root))
        storage.add_widget(storage_path)
        storage.add_widget(self.open_reports_root_button)
        self.open_reports_root_button.setVisible(True)
        self.settings_tabs.addTab(storage, "Storage")

        about = RelicPanel(
            "About",
            f"Relic Auditor v{__version__}\nLocal-first software appraisal with evidence-first safety boundaries.",
        )
        self.settings_tabs.addTab(about, "About")
        outer.addWidget(self.settings_tabs, 1)
        return shell

    def _build_technical_shell(self) -> QWidget:
        shell = QWidget()
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QFrame()
        toolbar.setObjectName("evidenceCard")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(
            SPACING.xl, SPACING.sm, SPACING.xl, SPACING.sm
        )
        self.back_to_product_button = SecondaryButton("Back to Answer")
        self.back_to_product_button.clicked.connect(self.close_technical_details)
        title_column = QVBoxLayout()
        title_column.setSpacing(0)
        self.technical_title = QLabel("Technical Evidence")
        self.technical_title.setObjectName("panelTitle")
        self.technical_context = QLabel("Viewing evidence for: no completed scan")
        self.technical_context.setObjectName("dimLabel")
        self.technical_context.setWordWrap(True)
        toolbar_layout.addWidget(self.back_to_product_button)
        title_column.addWidget(self.technical_title)
        title_column.addWidget(self.technical_context)
        toolbar_layout.addLayout(title_column)
        toolbar_layout.addStretch(1)
        layout.addWidget(toolbar)
        layout.addWidget(self._build_workspace(), 1)
        return shell

    def _build_sidebar(self) -> QWidget:
        """Reasoning configuration and provider diagnostics for Settings.

        The whole column scrolls, which is what keeps the provider panel
        reachable at 150%-200% scaling on a 768px-tall display.
        """

        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        column.setSpacing(SPACING.lg)

        config = RelicPanel(
            "Reasoning",
            "Advisory reasoning settings apply only to future audits.",
            emphasis=True,
        )
        config.add_widget(self.use_llm)

        self.provider_row = QVBoxLayout()
        self.provider_row.setSpacing(SPACING.xs)
        self.provider_row.addWidget(section_label("Reasoning provider"))
        self.provider_row.addWidget(self.llm_provider)
        self.provider_row.addWidget(self.llm_profile)

        claude_grid = QGridLayout()
        claude_grid.setHorizontalSpacing(SPACING.md)
        claude_grid.setVerticalSpacing(SPACING.xs)
        self.model_caption = section_label("Model")
        self.effort_caption = section_label("Effort")
        claude_grid.addWidget(self.model_caption, 0, 0)
        claude_grid.addWidget(self.effort_caption, 0, 1)
        claude_grid.addWidget(self.claude_model, 1, 0)
        claude_grid.addWidget(self.claude_effort, 1, 1)
        claude_grid.setColumnStretch(0, 1)
        claude_grid.setColumnStretch(1, 1)
        self.provider_row.addLayout(claude_grid)
        self.reasoning_speed_note = QLabel("")
        self.reasoning_speed_note.setObjectName("dimLabel")
        self.reasoning_speed_note.setWordWrap(True)
        self.provider_row.addWidget(self.reasoning_speed_note)
        config.add_layout(self.provider_row)
        column.addWidget(config)

        column.addWidget(self.provider_card)
        column.addStretch(1)

        scroller = QScrollArea()
        scroller.setWidget(content)
        scroller.setWidgetResizable(True)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroller.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroller.setFrameShape(QFrame.Shape.NoFrame)
        # Size the column from what the configuration content actually needs.
        # Guessing a width here is what previously clipped the Browse buttons,
        # the provider combo, and the provider status rows.
        # Clamped so the sidebar plus the workspace minimum still fit inside
        # the narrowest supported window; the column scrolls vertically for
        # anything that does not fit.
        # Two widths, not one. The MINIMUM stays tight so the sidebar plus the
        # workspace minimum still fit the narrowest supported window. The
        # PREFERRED width is what the configuration content actually wants, and
        # it is used whenever the window is wide enough - otherwise a roomy
        # display would still clip the Browse buttons and provider rows.
        needed = content.sizeHint().width() + SPACING.xl
        self._sidebar_minimum = max(340, min(needed, 405))
        self._sidebar_preferred = max(self._sidebar_minimum, min(needed, 460))
        scroller.setMinimumWidth(self._sidebar_minimum)
        scroller.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self.sidebar_scroll = scroller
        return scroller

    def _build_workspace(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.lg)

        layout.addWidget(self._build_metrics())

        self.technical_guide = QLabel(
            "Suggested order: Evidence Summary → Opportunities → Reusable Assets → "
            "Recommended Actions. Use System Map, Technical Truth, Reasoning, "
            "Duplicates, and Files when you need to verify the evidence."
        )
        self.technical_guide.setObjectName("mutedLabel")
        self.technical_guide.setWordWrap(True)
        self.technical_guide.setAccessibleName("Suggested technical review order")
        layout.addWidget(self.technical_guide)

        self.overview = OverviewWidget()
        self.architecture = ArchitectureView()
        self.technical = TechnicalTruthWidget()
        self.candidates = CandidateTable()
        self.duplicates = FindingsTable(
            [
                ("Hash", "sha256"),
                ("Copies", "copies"),
                ("Bytes each", "size_each"),
                ("Recoverable", "reclaimable_bytes_if_one_kept"),
                ("Paths", "paths"),
            ],
            placeholder="Filter duplicate groups…",
            empty_title="No byte-identical duplicates",
            empty_body="Nothing in this estate hashed to the same content.",
        )
        self.opportunities = FindingsTable(
            [
                ("Opportunity", "title"),
                ("Score", "overall_score"),
                ("Evidence", "evidence_score"),
                ("Readiness", "product_readiness_confidence"),
                ("Effort", "extraction_effort"),
                ("Buyer", "economic_buyer"),
                ("Summary", "summary"),
            ],
            placeholder="Filter product opportunities…",
            empty_title="No product opportunities",
            empty_body="Run Product Resurrection mode to rank offline opportunities.",
        )
        self.acquisition = FindingsTable(
            [
                ("Rank", "rank"),
                ("Capability", "title"),
                ("Path", "path"),
                ("Confidence", "confidence"),
                ("Context", "context"),
                ("Reusable", "reusable"),
                ("Evidence", "evidence"),
            ],
            placeholder="Filter acquisition candidates and evidence…",
            empty_title="No capability candidates",
            empty_body="Run Capability Acquisition mode to match reusable building blocks.",
        )
        self.llm_reasoning = FindingsTable(
            [("Section", "section"), ("Content", "content")],
            placeholder="Filter advisory reasoning…",
            empty_title="No advisory reasoning",
            empty_body=(
                "Enable advisory reasoning before running the audit. "
                "Deterministic reports never depend on it."
            ),
        )
        self.files = FindingsTable(
            [
                ("Path", "path"),
                ("Role", "role"),
                ("Ext", "extension"),
                ("Size", "size"),
                ("Source", "source"),
                ("Warnings", "warnings"),
            ],
            placeholder="Filter the observed file inventory…",
            empty_title="No files inspected yet",
            empty_body="Choose a target estate and run a read-only audit.",
        )

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        # Nine full-width tabs would otherwise force a ~1100px minimum on the
        # whole workspace and push the report actions off-screen. Let the bar
        # elide and scroll instead of dictating the window's minimum width.
        # Scroll rather than elide: "Ov…" / "Ar…" is unreadable, whereas a
        # scrollable bar keeps every label intact.
        self.tabs.setUsesScrollButtons(True)
        self.tabs.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setUsesScrollButtons(True)
        self.tabs.addTab(self.overview, "Evidence Summary")
        self.tabs.addTab(self.opportunities, "Opportunities")
        self.tabs.addTab(self.acquisition, "Reusable Assets")
        self.tabs.addTab(self.candidates, "Recommended Actions")
        self.tabs.addTab(self.architecture, "System Map")
        self.tabs.addTab(self.technical, "Technical Truth")
        self.tabs.addTab(self.llm_reasoning, "Reasoning")
        self.tabs.addTab(self.duplicates, "Duplicates")
        self.tabs.addTab(self.files, "Files")
        self.tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self._build_report_bar())
        return container

    def _build_metrics(self) -> QWidget:
        """Compact metric strip. Cards hug their content, never balloon."""

        wrapper = QFrame()
        wrapper.setObjectName("relicPanel")
        grid = QGridLayout(wrapper)
        grid.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
        grid.setHorizontalSpacing(SPACING.md)
        grid.setVerticalSpacing(SPACING.sm)

        self.metric_files = MetricCard("Files", "—", tone="neutral")
        self.metric_roots = MetricCard("Project roots", "—", tone="neutral")
        self.metric_candidates = MetricCard("Recommended Actions", "—")
        self.metric_acquisition = MetricCard("Reusable Assets", "—", tone="evidence")
        self.metric_llm = MetricCard("Advisory", "—", tone="evidence")
        self._metric_cards = [
            self.metric_files,
            self.metric_roots,
            self.metric_candidates,
            self.metric_acquisition,
            self.metric_llm,
        ]
        self._metric_grid = grid
        self._metrics_panel = wrapper
        wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout_metrics(columns=5)
        return wrapper

    def _fitting_metric_columns(self) -> int:
        """Widest metric row that actually fits the strip.

        Measured against the cards' own minimum widths rather than a width
        threshold. Guessing thresholds wrapped the strip to two rows while all
        five tiles would have fitted on one, which stole ~160px of height from
        the results workspace on a 768px display.
        """

        grid = self._metric_grid
        margins = grid.contentsMargins()
        available = self._metrics_panel.width() - margins.left() - margins.right()
        if available <= 0:
            return getattr(self, "_metric_columns", 5)
        spacing = grid.horizontalSpacing()
        for columns in (5, 3, 2):
            widest_run = max(
                sum(
                    card.minimumSizeHint().width()
                    for card in self._metric_cards[start : start + columns]
                )
                for start in range(0, len(self._metric_cards), columns)
            )
            if widest_run + (columns - 1) * spacing <= available:
                return columns
        return 2

    def _layout_metrics(self, columns: int) -> None:
        grid = self._metric_grid
        for card in self._metric_cards:
            grid.removeWidget(card)
        for index, card in enumerate(self._metric_cards):
            grid.addWidget(card, index // columns, index % columns)
        for column in range(max(columns, 1)):
            grid.setColumnStretch(column, 1)
        for column in range(columns, 6):
            grid.setColumnStretch(column, 0)
        self._metric_columns = columns

        # Reserve height for the actual number of rows. Without this the strip
        # keeps its single-row height when the grid wraps, and the second row
        # overlaps the first with its captions cropped.
        rows = -(-len(self._metric_cards) // max(columns, 1))
        tallest = max(card.minimumHeight() for card in self._metric_cards)
        margins = grid.contentsMargins()
        self._metrics_panel.setMinimumHeight(
            rows * tallest
            + (rows - 1) * grid.verticalSpacing()
            + margins.top()
            + margins.bottom()
        )

    def _build_report_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("evidenceCard")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(SPACING.md, SPACING.sm, SPACING.md, SPACING.sm)
        layout.setSpacing(SPACING.md)

        self.report_badge = StatusBadge("idle", "NOT EXPORTED")
        # Elides on one line: wrapping made this row grow very tall at narrow
        # widths, and reserving width for it pushed the buttons off-screen.
        self.report_label = ElidedLabel("Reports have not been exported yet.")
        self.report_label.setObjectName("mutedLabel")
        for button in (self.export_button, self.open_button):
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout.addWidget(self.report_badge)
        layout.addWidget(self.report_label, 1)
        layout.addWidget(self.export_button)
        layout.addWidget(self.open_button)
        return bar

    # -- responsive -------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not hasattr(self, "technical_shell"):
            return
        if self.shell_stack.currentWidget() is self.technical_shell:
            columns = self._fitting_metric_columns()
            if getattr(self, "_metric_columns", None) != columns:
                self._layout_metrics(columns)

    # -- provider ---------------------------------------------------------

    @Slot()
    def open_technical_details(
        self, opportunity_id: str | None = None
    ) -> None:
        """Reveal expert evidence and remember the exact originating surface."""

        origin = self.shell_stack.currentWidget()
        if origin is not self.technical_shell:
            self._technical_origin = origin
        if origin is not self.technical_shell:
            self._technical_opportunity_id = opportunity_id
        target = (
            self.bundle.audit.target.name
            if self.bundle is not None
            else "no completed scan"
        )
        context = f"Viewing evidence for: {target}"
        opportunity = self._opportunity_by_id(self._technical_opportunity_id)
        if opportunity is not None:
            context += "\nScoped to opportunity: " + product_friendly_title(
                str(opportunity.get("title") or "Focused product opportunity")
            )
        self.technical_context.setText(context)
        self._scope_technical_opportunities(self._technical_opportunity_id)
        if origin is self.product_shell and self.flow.state is FlowState.OPPORTUNITY_CHOOSER:
            self.back_to_product_button.setText("Back to Opportunity")
        elif origin is self.product_shell and self.flow.state is FlowState.PREPARE_PRODUCT:
            self.back_to_product_button.setText("Back to Product Plan")
        elif origin is self.product_shell and self.flow.state is FlowState.BUILD_PACK_READY:
            self.back_to_product_button.setText("Back to Build Pack")
        elif origin is self.product_shell and self.flow.state in {
            FlowState.ANSWER_READY,
            FlowState.OPPORTUNITY_SELECTED,
        }:
            self.back_to_product_button.setText("Back to Answer")
        elif origin is self.settings_shell:
            self.back_to_product_button.setText("Back to Settings")
        else:
            self.back_to_product_button.setText("Back")
        self.shell_stack.setCurrentWidget(self.technical_shell)
        self.status_message.setText("Technical Evidence · expert view")

    @Slot()
    def close_technical_details(self) -> None:
        destination = self._technical_origin or self.product_shell
        self.shell_stack.setCurrentWidget(destination)
        self._scope_technical_opportunities(None)
        self.status_message.setText("Ready")

    def _set_flow_state(
        self, state: FlowState, *, new_workflow: bool = False
    ) -> None:
        self.flow.transition(state, new_workflow=new_workflow)
        page = {
            FlowState.NO_TARGET: self.scan_page,
            FlowState.TARGET_SELECTED: self.scan_page,
            FlowState.SCANNING: self.scanning_page,
            FlowState.ANSWER_READY: self.answer_page,
            FlowState.OPPORTUNITY_CHOOSER: self.opportunity_page,
            FlowState.OPPORTUNITY_SELECTED: self.answer_page,
            FlowState.PREPARE_PRODUCT: self.prepare_page,
            FlowState.BUILD_PACK_GATE: self.build_pack_gate_page,
            FlowState.BUILD_PACK_READY: self.build_pack_page,
            FlowState.BUILD_SESSION_ACTIVE: self.build_pack_page,
        }[state]
        self.flow_stack.setCurrentWidget(page)
        self.shell_stack.setCurrentWidget(self.product_shell)
        self.run_button.setEnabled(
            state == FlowState.TARGET_SELECTED and bool(self.target_selector.path())
        )

    @Slot()
    def open_history(self) -> None:
        self.refresh_report_history()
        self.shell_stack.setCurrentWidget(self.history_shell)
        self.status_message.setText("History · previous completed scans")

    @Slot()
    def open_settings(self) -> None:
        self.shell_stack.setCurrentWidget(self.settings_shell)
        self.status_message.setText("Settings")

    @Slot()
    def open_scan_settings(self) -> None:
        self.open_settings()
        self.settings_tabs.setCurrentWidget(self.settings_scan_tab)

    @Slot()
    def close_secondary_surface(self) -> None:
        self.shell_stack.setCurrentWidget(self.product_shell)
        self.status_message.setText("Ready")

    def _opportunity_by_id(self, opportunity_id: str | None):
        if (
            not opportunity_id
            or self.bundle is None
            or self.bundle.discovery is None
        ):
            return None
        return next(
            (
                item
                for item in self.bundle.discovery.opportunities
                if str(item.get("opportunity_id") or "") == opportunity_id
            ),
            None,
        )

    def _load_opportunity_cards(self) -> None:
        """Populate the compact, single-action opportunity chooser."""

        self.opportunity_list.clear()
        if self.bundle is None or self.bundle.discovery is None:
            self.opportunity_count_label.setText("No completed opportunity analysis.")
            self.choose_opportunity_button.setEnabled(False)
            self.chooser_evidence_button.setEnabled(False)
            self.opportunity_preview.set_body("No opportunity is available to compare.")
            return

        opportunities = list(self.bundle.discovery.opportunities)
        count = len(opportunities)
        noun = "direction" if count == 1 else "directions"
        self.opportunity_count_label.setText(
            f"Compare {count:,} product {noun} for {self.bundle.audit.target.name}. "
            "Choose a row, then use the single primary action below."
        )
        selected_row = 0
        for index, opportunity in enumerate(opportunities):
            opportunity_id = str(opportunity.get("opportunity_id") or "")
            title = product_friendly_title(
                str(opportunity.get("title") or "Focused product opportunity")
            )
            rank = "Best fit" if index == 0 else (
                "Strong alternative" if index == 1 else "Alternative"
            )
            if opportunity_id == self._selected_opportunity_id:
                rank = f"Selected · {rank}"
            reusable_count = len(opportunity.get("reusable_assets") or [])
            asset_word = "asset" if reusable_count == 1 else "assets"
            confidence = str(
                opportunity.get("evidence_strength") or "exploratory"
            ).replace("_", " ").title()
            effort = str(opportunity.get("extraction_effort") or "not estimated")
            item = QListWidgetItem(
                f"{index + 1}. {title}\n"
                f"{rank} · {confidence} evidence · {effort} effort · "
                f"{reusable_count:,} reusable {asset_word}"
            )
            item.setData(Qt.ItemDataRole.UserRole, opportunity_id)
            item.setToolTip(
                str(
                    opportunity.get("summary")
                    or "Review the available evidence for this product direction."
                )
            )
            item.setData(
                Qt.ItemDataRole.AccessibleTextRole,
                f"Rank {index + 1}, {title}, {rank}, {confidence} evidence, "
                f"{effort} effort, {reusable_count} reusable {asset_word}",
            )
            self.opportunity_list.addItem(item)
            if opportunity_id == self._selected_opportunity_id:
                selected_row = index
        if count:
            self.opportunity_list.setCurrentRow(selected_row)
            self._preview_opportunity_choice()

    def _chooser_opportunity_id(self) -> str | None:
        item = self.opportunity_list.currentItem()
        if item is None:
            return None
        return str(item.data(Qt.ItemDataRole.UserRole) or "") or None

    @Slot()
    def _preview_opportunity_choice(self) -> None:
        opportunity = self._opportunity_by_id(self._chooser_opportunity_id())
        enabled = opportunity is not None
        self.choose_opportunity_button.setEnabled(enabled)
        self.chooser_evidence_button.setEnabled(enabled)
        if opportunity is None:
            self.opportunity_preview.title_label.setText("SELECTED OPPORTUNITY")
            self.opportunity_preview.set_body("Choose a row to compare its complete summary.")
            return
        title = product_friendly_title(
            str(opportunity.get("title") or "Focused product opportunity")
        )
        reusable_count = len(opportunity.get("reusable_assets") or [])
        asset_word = "asset is" if reusable_count == 1 else "assets are"
        self.opportunity_preview.title_label.setText(title)
        self.opportunity_preview.set_body(
            str(
                opportunity.get("summary")
                or "Review the available evidence for this product direction."
            )
            + f"\n\n{reusable_count:,} reusable {asset_word} linked to this direction."
        )

    @Slot()
    def select_chooser_opportunity(self) -> None:
        opportunity_id = self._chooser_opportunity_id()
        if opportunity_id:
            self.select_opportunity(opportunity_id)

    @Slot()
    def open_chooser_opportunity_evidence(self) -> None:
        opportunity_id = self._chooser_opportunity_id()
        if opportunity_id:
            self.open_opportunity_evidence(opportunity_id)

    @Slot()
    def open_opportunity_chooser(self) -> None:
        if (
            self.bundle is None
            or self.bundle.discovery is None
            or not self.bundle.discovery.opportunities
        ):
            return
        self._load_opportunity_cards()
        self._set_flow_state(FlowState.OPPORTUNITY_CHOOSER)
        self.status_message.setText("Choose a product opportunity")

    def select_opportunity(self, opportunity_id: str) -> None:
        if self._opportunity_by_id(opportunity_id) is None or self.bundle is None:
            return
        self._selected_opportunity_id = opportunity_id
        self._opportunity_was_selected = True
        self._load_plain_english_results(self.bundle)
        self._set_flow_state(FlowState.OPPORTUNITY_SELECTED)
        self.status_message.setText("Answer updated for the selected opportunity")

    def open_opportunity_evidence(self, opportunity_id: str) -> None:
        if self._opportunity_by_id(opportunity_id) is None:
            return
        self.open_technical_details(opportunity_id)
        self.tabs.setCurrentWidget(self.opportunities)

    def _scope_technical_opportunities(self, opportunity_id: str | None) -> None:
        """Keep the evidence table, tab count, selection, and detail in one scope."""

        rows = list(self._all_opportunity_rows)
        if opportunity_id:
            rows = [
                row
                for row in rows
                if str(row.get("opportunity_id") or "") == opportunity_id
            ]
        self.opportunities.set_rows(rows)
        label = f"Opportunities ({len(rows)}"
        if opportunity_id and rows:
            label += " scoped"
            self.opportunities.select_row(0)
        self.tabs.setTabText(self.tabs.indexOf(self.opportunities), label + ")")

    @Slot()
    def toggle_update_diagnostics(self) -> None:
        visible = not self.update_diagnostic_label.isVisible()
        self.update_diagnostic_label.setVisible(visible)
        self.update_diagnostics_button.setText(
            "Hide technical diagnostics" if visible else "Show technical diagnostics"
        )

    @Slot()
    def toggle_other_opportunities(self) -> None:
        """Compatibility slot retained for the original focused-flow button."""

        self.open_opportunity_chooser()

    @Slot()
    def return_to_answer(self) -> None:
        if self.bundle is not None:
            state = (
                FlowState.OPPORTUNITY_SELECTED
                if self._opportunity_was_selected
                else FlowState.ANSWER_READY
            )
            self._set_flow_state(state)

    @Slot()
    def return_to_prepare(self) -> None:
        if self.bundle is not None:
            self._set_flow_state(FlowState.PREPARE_PRODUCT)

    @Slot()
    def open_selected_opportunity_evidence(self) -> None:
        self.open_technical_details(self._selected_opportunity_id)

    @Slot()
    def open_reusable_assets_evidence(self) -> None:
        self.open_technical_details()
        self.tabs.setCurrentWidget(self.acquisition)

    @Slot()
    @Slot(int)
    def _update_reasoning_speed_note(self, _index: int | None = None) -> None:
        model = str(self.claude_model.currentData() or "sonnet")
        effort = str(self.claude_effort.currentData() or DEFAULT_EFFORT)
        if model == "opus" and effort == "high":
            self.reasoning_speed_note.setText(
                "Opus + high is the slowest option and can exceed the 90-second "
                "advisory limit. Sonnet + medium is recommended for most audits."
            )
            self.reasoning_speed_note.setToolTip(
                "A timeout affects advisory reasoning only; deterministic results remain complete."
            )
        else:
            self.reasoning_speed_note.setText(
                "Recommended starting point: Sonnet + medium. Advisory reasoning "
                "is optional and never blocks deterministic results."
            )
            self.reasoning_speed_note.setToolTip("")

    def _claude_max_selected(self) -> bool:
        return self.llm_provider.currentData() == "claude-max"

    @Slot()
    def _update_llm_controls(self) -> None:
        enabled = self.use_llm.isChecked()
        claude = self._claude_max_selected()
        self.llm_provider.setEnabled(enabled)
        self.llm_profile.setVisible(enabled and not claude)
        self.llm_profile.setEnabled(enabled and not claude)
        for widget in (
            self.claude_model,
            self.claude_effort,
            self.model_caption,
            self.effort_caption,
        ):
            widget.setVisible(enabled and claude)
            widget.setEnabled(enabled)
        self.provider_card.setVisible(True)
        self.provider_card.check_button.setEnabled(True)
        self.provider_card.login_button.setEnabled(True)
        self._update_reasoning_speed_note()

    @Slot()
    def _refresh_provider(self, initial: bool = False) -> None:
        try:
            status = claude_max_status(DEFAULT_CLAUDE_MAX_PROFILE)
        except (ClaudeCodeError, OSError, ValueError) as exc:
            self.provider_card.set_message(str(exc), "failed")
            self.provider_badge.set_status("failed", "PROVIDER: ERROR")
            self._provider_configured = False
            return
        status = dict(status)
        status["model"] = self.claude_model.currentData() or status.get("model")
        status["effort"] = self.claude_effort.currentData() or status.get("effort")
        self.provider_card.set_status(status)
        self._provider_configured = bool(status.get("ready"))
        if status.get("ready"):
            runtime = load_provider_health("claude-code")
            if runtime.status in {"failed", "running"}:
                interrupted = runtime.status == "running"
                label = "INTERRUPTED" if interrupted else "LAST REQUEST FAILED"
                message = (
                    "The previous Claude request did not finish."
                    if interrupted
                    else runtime.message or "The previous Claude request failed."
                )
                self.provider_badge.set_status("failed", f"CLAUDE: {label}")
                self.provider_card.set_runtime_status(
                    "failed",
                    label,
                    f"{message} Setup is configured, but runtime is not operational.",
                )
            elif runtime.status == "operational":
                self.provider_badge.set_status("ready", "CLAUDE: OPERATIONAL")
                self.provider_card.set_runtime_status(
                    "ready",
                    "OPERATIONAL",
                    "The last Claude advisory request completed successfully. "
                    "Use Check Claude setup to revalidate configuration.",
                )
            else:
                self.provider_badge.set_status("active", "CLAUDE: CONFIGURED")
                self.provider_card.set_message(
                    "Claude Code is installed and the subscription session is signed in. "
                    "Operational status is confirmed only after a reasoning request succeeds.",
                    "active",
                )
        elif not status.get("executable_found"):
            self.provider_badge.set_status("idle", "PROVIDER: ABSENT")
            self.provider_card.set_message(
                "Claude Code is not installed or not on PATH. Deterministic "
                "analysis works without it.",
                "advisory",
            )
        elif not status.get("logged_in"):
            self.provider_badge.set_status("warning", "PROVIDER: SIGNED OUT")
            self.provider_card.set_message(
                "Claude Code is installed but signed out. Use Open Claude login.",
                "advisory",
            )
        elif status.get("authentication_type") == "api-key":
            self.provider_badge.set_status("warning", "PROVIDER: API KEY")
            self.provider_card.set_message(
                "Signed in with a Console/API key, not a Claude.ai subscription. "
                "Run 'claude auth logout' then log in with your Claude.ai account.",
                "warning",
            )
        else:
            self.provider_badge.set_status("warning", "PROVIDER: UNCONFIRMED")
            self.provider_card.set_message(
                "A subscription session could not be confirmed.", "advisory"
            )

    @Slot()
    def open_claude_login(self) -> None:
        try:
            code = launch_claude_login()
        except (ClaudeCodeError, OSError) as exc:
            self.provider_card.set_message(str(exc), "failed")
            self.provider_badge.set_status("failed", "CLAUDE: LOGIN ERROR")
            return
        if code == 0:
            self.provider_card.set_message(
                "Login flow finished. Re-check the provider to confirm.", "ready"
            )
        else:
            self.provider_card.set_message(
                f"'claude auth login' exited with status {code}.", "failed"
            )
            self.provider_badge.set_status("failed", "CLAUDE: LOGIN FAILED")

    # -- scanning ---------------------------------------------------------

    def _target_changed(self, text: str) -> None:
        selected = text.strip()
        self.source_reassurance.setVisible(bool(selected))
        if self._scan_thread is not None:
            return
        if selected:
            chosen = Path(selected).expanduser().resolve()
            if self.bundle is not None and chosen != self.bundle.audit.target.resolve():
                self.bundle = None
                self._selected_opportunity_id = None
                self._opportunity_was_selected = False
                self.report_directory = None
                self._prepared_build_pack = None
                self._exported_build_pack = None
                self.results_empty.setVisible(True)
                self.results_content.setVisible(False)
            self.status_message.setText(f"Ready to scan {chosen.name}")
            self._set_flow_state(FlowState.TARGET_SELECTED, new_workflow=True)
        else:
            self.bundle = None
            self._selected_opportunity_id = None
            self._opportunity_was_selected = False
            self._prepared_build_pack = None
            self._exported_build_pack = None
            self.status_message.setText("Choose a folder to begin")
            self._set_flow_state(FlowState.NO_TARGET, new_workflow=True)

    @Slot()
    def start_scan(self) -> None:
        # A second click while a scan is live must never start another one.
        if self._scan_thread is not None:
            return
        raw = self.target_selector.path()
        if not raw:
            QMessageBox.information(
                self, "Choose a folder", "Select a target estate to audit first."
            )
            return
        target = Path(raw).expanduser()
        profile = None
        if self.use_llm.isChecked():
            if self._claude_max_selected():
                try:
                    profile = ensure_claude_max_profile(
                        DEFAULT_CLAUDE_MAX_PROFILE,
                        model=str(self.claude_model.currentData()),
                        effort=str(self.claude_effort.currentData()),
                    ).name
                except (ClaudeCodeError, OSError, ValueError) as exc:
                    QMessageBox.warning(
                        self,
                        "Claude Code / Claude Max",
                        f"Could not prepare the Claude Max profile: {exc}",
                    )
                    return
            else:
                profile = self.llm_profile.text().strip()
                if not profile:
                    QMessageBox.information(
                        self,
                        "Choose an LLM profile",
                        "Enter a configured profile name or turn off advisory reasoning.",
                    )
                    return
        mode = self.mode.currentData()
        options = DashboardOptions(
            include_hidden=self.include_hidden.isChecked(),
            technical_truth=mode in {"full", "truth", "resurrection"},
            product_discovery=mode in {"full", "resurrection"},
            capability_acquisition=mode in {"full", "acquisition"},
            llm_profile=profile,
        )

        self.bundle = None
        self.report_directory = None
        self._prepared_build_pack = None
        self._exported_build_pack = None
        self.export_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.view_full_report_button.setEnabled(False)
        self.results_empty.setVisible(True)
        self.results_content.setVisible(False)
        self.report_badge.set_status("idle", "NOT EXPORTED")
        self.report_label.setText("Reports have not been exported yet.")
        self._set_config_enabled(False)
        self.scanning_title.setText(f"Analyzing {target.name}…")
        self._set_flow_state(FlowState.SCANNING)
        if self.use_llm.isChecked() and self._claude_max_selected():
            try:
                save_provider_health(
                    "claude-code", "running", "Claude advisory request started."
                )
            except OSError:
                pass
            self.provider_badge.set_status("running", "CLAUDE: RUNNING")
            self.provider_card.set_runtime_status(
                "running",
                "RUNNING",
                "Claude advisory reasoning is running. Deterministic analysis continues independently.",
            )
        self._scan_started_at = time.monotonic()
        self._elapsed_timer.start()
        self.scan_panel.set_running("Starting read-only audit…", 0)
        # Elapsed starts counting immediately; file and root counts are not
        # known until the engine reports them, so they stay "not measured".
        self.scan_panel.set_counters("0s", None, None)

        thread = QThread(self)
        worker = ScanWorker(target, options, self.entitlement)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._scan_progress)
        worker.finished.connect(self._scan_complete)
        worker.failed.connect(self._scan_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._scan_thread = thread
        self._scan_worker = worker
        thread.start()

    @Slot()
    def cancel_scan(self) -> None:
        if self._scan_worker is not None:
            self._scan_worker.cancel()
            self.scan_panel.set_running("Cancelling…", None)

    def _set_config_enabled(self, enabled: bool) -> None:
        self.run_button.setEnabled(
            enabled
            and self.flow.state == FlowState.TARGET_SELECTED
            and bool(self.target_selector.path())
        )
        self.target_selector.setEnabled(enabled)
        self.mode.setEnabled(enabled)
        self.include_hidden.setEnabled(enabled)
        self.use_llm.setEnabled(enabled)
        self.llm_provider.setEnabled(enabled and self.use_llm.isChecked())
        self.llm_profile.setEnabled(
            enabled and self.use_llm.isChecked() and not self._claude_max_selected()
        )
        self.claude_model.setEnabled(enabled)
        self.claude_effort.setEnabled(enabled)

    def _tick_elapsed(self) -> None:
        if self._scan_started_at is None:
            return
        seconds = int(time.monotonic() - self._scan_started_at)
        minutes, remainder = divmod(seconds, 60)
        text = f"{minutes}m {remainder:02d}s" if minutes else f"{remainder}s"
        self.scan_panel.elapsed_card.set_value(text)

    @Slot(int, str)
    def _scan_progress(self, value: int, message: str) -> None:
        # The engine reports coarse checkpoints; anything between them is
        # genuinely unknown, so show motion rather than a made-up number.
        self.scan_panel.set_running(message, value if value > 0 else None)

    @Slot(object)
    def _scan_complete(self, bundle: DashboardBundle) -> None:
        self.bundle = bundle
        self._selected_opportunity_id = None
        self._opportunity_was_selected = False
        self._elapsed_timer.stop()
        self._load_bundle(bundle)
        files = len(bundle.audit.files)
        roots = len(bundle.audit.projects)
        self.scan_panel.set_complete(
            f"Audit complete. {files:,} files inspected across {roots:,} project "
            "roots. The target was not modified."
        )
        self.scan_panel.files_card.set_value(f"{files:,}")
        self.scan_panel.roots_card.set_value(f"{roots:,}")
        self.export_button.setEnabled(True)
        self._load_plain_english_results(bundle)
        self._auto_export_reports(bundle)
        self.refresh_report_history()
        self.tabs.setCurrentWidget(self.overview)
        self._set_flow_state(FlowState.ANSWER_READY)
        self.status_message.setText(f"Answer ready · {bundle.audit.target.name}")

    @Slot(str)
    def _scan_failed(self, message: str) -> None:
        self._elapsed_timer.stop()
        if message == "__cancelled__":
            self.scan_panel.set_cancelled()
            self._set_flow_state(FlowState.TARGET_SELECTED)
            self.status_message.setText("Scan cancelled · source was not modified")
            return
        self.scan_panel.set_failed(f"Audit failed: {message}")
        self._set_flow_state(FlowState.TARGET_SELECTED)
        self.status_message.setText("Scan failed · review the error and retry")
        QMessageBox.critical(self, "Relic audit failed", message)

    @Slot()
    def _thread_finished(self) -> None:
        self._scan_thread = None
        self._scan_worker = None
        self._scan_started_at = None
        self._elapsed_timer.stop()
        self._set_config_enabled(True)
        self._update_llm_controls()
        if self._close_when_done:
            self.close()

    # -- results ----------------------------------------------------------

    def _load_bundle(self, bundle: DashboardBundle) -> None:
        self.overview.load_bundle(bundle)
        self.architecture.load_bundle(bundle)
        self.technical.load_bundle(bundle)
        self.candidates.load_bundle(bundle)
        self.duplicates.set_rows(
            [{**item, "_raw": item} for item in bundle.audit.duplicate_groups]
        )
        opportunities = bundle.discovery.opportunities if bundle.discovery else []
        self._all_opportunity_rows = [
            {**item, "_raw": item} for item in opportunities
        ]
        self.opportunities.set_rows(self._all_opportunity_rows)
        acquisition = bundle.acquisition.best_candidates if bundle.acquisition else []
        self.acquisition.set_rows([{**item, "_raw": item} for item in acquisition])

        reasoning_rows: list[dict[str, object]] = []
        if bundle.llm_reasoning is not None:
            reasoning_rows.append(
                {"section": "Summary", "content": bundle.llm_reasoning.narrative}
            )
            for section, content in bundle.llm_reasoning.analysis.items():
                reasoning_rows.append(
                    {"section": section.replace("_", " ").title(), "content": content}
                )
            if bundle.llm_reasoning.error:
                reasoning_rows.append(
                    {"section": "Provider error", "content": bundle.llm_reasoning.error}
                )
                # Setup availability and request success are separate states.
                # A real request failure must override every optimistic setup
                # badge so the interface never says READY after a timeout.
                error = bundle.llm_reasoning.error
                timed_out = "timed out" in error.casefold()
                label = "TIMED OUT" if timed_out else "FAILED"
                provider_name = (
                    "CLAUDE"
                    if bundle.llm_reasoning.protocol == "claude-code"
                    else "PROVIDER"
                )
                self.provider_badge.set_status("failed", f"{provider_name}: {label}")
                self.provider_card.set_runtime_status(
                    "failed",
                    label,
                    f"Advisory reasoning unavailable: {error}. "
                    "Deterministic audit results and saved reports remain complete.",
                )
                if bundle.llm_reasoning.protocol == "claude-code":
                    try:
                        save_provider_health("claude-code", "failed", error)
                    except OSError:
                        pass
            elif bundle.llm_reasoning.status == "complete":
                provider_name = (
                    "CLAUDE"
                    if bundle.llm_reasoning.protocol == "claude-code"
                    else "PROVIDER"
                )
                self.provider_badge.set_status(
                    "ready", f"{provider_name}: OPERATIONAL"
                )
                self.provider_card.set_runtime_status(
                    "ready",
                    "OPERATIONAL",
                    "Claude advisory reasoning completed successfully for this audit.",
                )
                if bundle.llm_reasoning.protocol == "claude-code":
                    try:
                        save_provider_health(
                            "claude-code",
                            "operational",
                            "Claude advisory reasoning completed successfully.",
                        )
                    except OSError:
                        pass
        self.llm_reasoning.set_rows([{**item, "_raw": item} for item in reasoning_rows])
        self.files.set_rows(
            [
                {**public_record(record), "_raw": public_record(record)}
                for record in bundle.audit.files
            ]
        )

        candidate_total = (
            len(bundle.audit.extract_candidates)
            + len(bundle.audit.archive_candidates)
            + len(bundle.audit.delete_candidates)
        )
        self.metric_files.set_value(f"{len(bundle.audit.files):,}")
        self.metric_roots.set_value(f"{len(bundle.audit.projects):,}")
        self.metric_candidates.set_value(f"{candidate_total:,}")
        self.metric_acquisition.set_value(f"{len(acquisition):,}")
        self.metric_llm.set_value(f"{len(reasoning_rows):,}")

        self.tabs.setTabText(
            self.tabs.indexOf(self.candidates),
            f"Recommended Actions ({candidate_total})",
        )
        self.tabs.setTabText(
            self.tabs.indexOf(self.duplicates),
            f"Duplicates ({len(bundle.audit.duplicate_groups)})",
        )
        self.tabs.setTabText(
            self.tabs.indexOf(self.opportunities),
            f"Opportunities ({len(opportunities)})",
        )
        self.tabs.setTabText(
            self.tabs.indexOf(self.acquisition), f"Reusable Assets ({len(acquisition)})"
        )
        self.tabs.setTabText(
            self.tabs.indexOf(self.llm_reasoning), f"Reasoning ({len(reasoning_rows)})"
        )
        self.tabs.setTabText(
            self.tabs.indexOf(self.files), f"Files ({len(bundle.audit.files)})"
        )

    def _load_plain_english_results(self, bundle: DashboardBundle) -> None:
        answer = focused_answer(bundle, self._selected_opportunity_id)
        self._selected_opportunity_id = str(answer["opportunity_id"] or "") or None
        self.answer_conclusion.setText(str(answer["conclusion"]))
        self.answer_detail.setText(str(answer["detail"]))
        self.best_opportunity_card.title_label.setText("BEST OPPORTUNITY")
        self.best_opportunity_card.set_body(
            f"{answer['opportunity_title']}\n\n{answer['opportunity_summary']}"
        )
        reusable_count = int(answer["reusable_count"])
        concern_count = int(answer["concern_count"])
        asset_word = "asset" if reusable_count == 1 else "assets"
        item_word = "item" if concern_count == 1 else "items"
        attention = "needs" if concern_count == 1 else "need"
        self.answer_supporting_summary.setText(
            f"{reusable_count:,} reusable {asset_word} · {concern_count:,} "
            f"{item_word} {attention} attention"
        )
        self.answer_recommendation_label.setText(str(answer["recommendation"]))
        self.results_empty.setVisible(False)
        self.results_content.setVisible(True)
        opportunities = list(answer["opportunities"])
        self.other_opportunities_button.setVisible(len(opportunities) > 1)
        has_opportunity = bool(opportunities)
        self.prepare_product_button.setVisible(has_opportunity)
        self.prepare_product_button.setEnabled(has_opportunity)
        self.prepare_product_button.setToolTip("")

    @Slot()
    def manage_plan(self) -> None:
        dialog = LicenseDialog(self.entitlement, self)
        dialog.entitlement_changed.connect(self._entitlement_changed)
        dialog.exec()

    @Slot(object)
    def _entitlement_changed(self, entitlement: Entitlement) -> None:
        self.entitlement = entitlement
        if self.bundle is not None:
            self.bundle.entitlement = entitlement
            self._load_plain_english_results(self.bundle)
        self.plan_badge.set_status(
            "ready" if entitlement.license_id else "idle",
            f"PLAN: {entitlement.tier.value.upper()}",
        )

    @Slot()
    def prepare_leading_product(self) -> None:
        if (
            self.bundle is None
            or self.bundle.discovery is None
            or not self.bundle.discovery.opportunities
        ):
            return
        answer = focused_answer(self.bundle, self._selected_opportunity_id)
        self.prepare_heading.setText(f"Prepare {answer['opportunity_title']}")
        self.prepare_product_card.set_body(
            str(answer["opportunity_summary"])
        )
        self.prepare_reuse_card.set_body(str(answer["reusable"]))
        missing = answer["missing"]
        self.prepare_missing_card.set_body(
            "\n".join(f"• {item}" for item in missing)
            if missing
            else "No MVP-critical missing component was identified."
        )
        self.prepare_mvp_card.set_body(str(answer["mvp"]))
        risks = answer["risks"]
        self.prepare_risks_card.set_body(
            "\n".join(f"• {item}" for item in risks)
            if risks
            else "Exact asset provenance and approvals remain required."
        )
        self._set_flow_state(FlowState.PREPARE_PRODUCT)
        self.status_message.setText("Review the product definition before creating a Build Pack")

    @Slot()
    def create_build_pack(self) -> None:
        if (
            self.bundle is None
            or self.bundle.discovery is None
            or not self.bundle.discovery.opportunities
        ):
            return
        if not self.entitlement.allows(ProductCapability.BUILD_PACK_PREVIEW):
            self.build_pack_gate_message.setText(
                "Build Pack creation requires Premium. Your product plan remains available."
            )
            self._set_flow_state(FlowState.BUILD_PACK_GATE)
            self.status_message.setText("Premium is required to create a Build Pack")
            return
        service = BuildPackService(self.entitlement)
        opportunity = self._opportunity_by_id(self._selected_opportunity_id)
        if opportunity is None:
            return
        try:
            pack = service.prepare(
                self.bundle.discovery,
                opportunity["opportunity_id"],
                audit=self.bundle.audit,
                source_root=self.bundle.audit.target,
            )
            output = (self.report_directory or self.reports_root) / "Build Packs"
            dialog = BuildPackDialog(service, pack, output, self)
            if dialog.exec():
                exported = dialog.export_selected()
                self._build_pack_service = service
                self._prepared_build_pack = pack
                self._exported_build_pack = exported
                self.open_build_pack_button.setEnabled(True)
                self.start_assisted_build_button.setEnabled(True)
                self.build_pack_summary.set_body(
                    "Product brief\nMVP scope\nArchitecture\nImplementation plan\n"
                    "Reusable asset manifest\nAcceptance criteria\nBuilder handoff\n\n"
                    f"Verified export: {exported.directory}"
                )
                self._set_flow_state(FlowState.BUILD_PACK_READY)
                self.status_message.setText(f"Build Pack ready · {exported.directory}")
        except PermissionError:
            self._set_flow_state(FlowState.BUILD_PACK_GATE)
            self.status_message.setText("Premium is required to create a Build Pack")
        except ValueError:
            QMessageBox.warning(
                self,
                "Build Pack not ready",
                "This product direction needs stronger evidence before Relic can "
                "prepare its Build Pack safely.",
            )
        except OSError:
            QMessageBox.warning(
                self,
                "Build Pack unavailable",
                "Relic could not prepare the Build Pack workspace. No source files "
                "were changed.",
            )

    @Slot()
    def open_exported_build_pack(self) -> None:
        if self._exported_build_pack is not None:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self._exported_build_pack.directory))
            )

    @Slot()
    def start_assisted_build(self) -> None:
        if self.bundle is None or self._exported_build_pack is None:
            return
        output = (self.report_directory or self.reports_root) / "Build Sessions"
        self._set_flow_state(FlowState.BUILD_SESSION_ACTIVE)
        try:
            AssistedBuildDialog(
                self.bundle.entitlement,
                self._exported_build_pack.directory,
                output,
                self,
            ).exec()
        finally:
            self._set_flow_state(FlowState.BUILD_PACK_READY)

    def _auto_export_reports(self, bundle: DashboardBundle) -> None:
        """Persist a completed scan in Relic's stable report history."""

        destination = automatic_report_directory(bundle.audit.target, self.reports_root)
        try:
            written = export_dashboard_bundle(
                bundle, destination, self.candidates.decisions
            )
        except (ValueError, OSError) as exc:
            self.report_directory = None
            self.view_full_report_button.setEnabled(False)
            self.open_button.setEnabled(False)
            self.report_badge.set_status("failed", "AUTO-SAVE FAILED")
            self.report_label.setText(str(exc))
            self.status_message.setText(f"Audit complete · Report save failed: {exc}")
            return

        self.report_directory = destination.resolve()
        self.view_full_report_button.setEnabled(self._full_report_path() is not None)
        self.open_button.setEnabled(True)
        self.report_badge.set_status("success", "SAVED")
        self.report_label.setText(
            f"Saved {len(written)} reports to {self.report_directory}"
        )
        self.report_label.setToolTip(str(self.report_directory))
        self.status_message.setText(
            f"Audit complete · Reports saved for {bundle.audit.target.name}"
        )

    def _full_report_path(self) -> Path | None:
        if self.report_directory is None:
            return None
        for name in (
            "estate-report.md",
            "technical_truth_report.md",
            "product_resurrection_brief.md",
        ):
            candidate = self.report_directory / name
            if candidate.is_file():
                return candidate
        markdown = sorted(self.report_directory.glob("*.md"))
        return markdown[0] if markdown else None

    @Slot()
    def view_full_report(self) -> None:
        report = self._full_report_path()
        if report is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(report)))

    @Slot()
    def refresh_report_history(self) -> None:
        self._history_entries = list_report_history(self.reports_root)
        self.reports_list.clear()
        for entry in self._history_entries:
            label = f"{entry.project}  ·  {entry.scan.replace('_', ' ')}"
            item = QListWidgetItem(label)
            item.setToolTip(str(entry.directory))
            item.setData(Qt.ItemDataRole.UserRole, str(entry.directory))
            item.setData(
                Qt.ItemDataRole.UserRole + 1,
                str(entry.full_report) if entry.full_report else "",
            )
            self.reports_list.addItem(item)
        available = bool(self._history_entries)
        self.reports_empty.setVisible(not available)
        self.reports_list.setVisible(available)
        self.open_selected_report_button.setEnabled(available)
        self.open_selected_folder_button.setEnabled(available)
        if available:
            self.reports_list.setCurrentRow(0)

    def _selected_history_paths(self) -> tuple[Path | None, Path | None]:
        item = self.reports_list.currentItem()
        if item is None:
            return None, None
        directory_text = str(item.data(Qt.ItemDataRole.UserRole) or "")
        report_text = str(item.data(Qt.ItemDataRole.UserRole + 1) or "")
        return (
            Path(directory_text) if directory_text else None,
            Path(report_text) if report_text else None,
        )

    @Slot()
    def open_reports_root(self) -> None:
        try:
            self.reports_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Reports folder", str(exc))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.reports_root.resolve())))

    @Slot()
    def open_selected_report(self) -> None:
        _directory, report = self._selected_history_paths()
        if report is not None and report.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(report)))

    @Slot()
    def open_selected_report_folder(self) -> None:
        directory, _report = self._selected_history_paths()
        if directory is not None and directory.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    @Slot()
    def export_reports(self) -> None:
        if self.bundle is None:
            return
        target = self.bundle.audit.target
        suggested = Path(self.output_selector.path() or "") or None
        if not self.output_selector.path():
            suggested = target.parent / f"{target.name}-relic-report"
        selected = QFileDialog.getExistingDirectory(
            self,
            "Choose or create the report directory",
            str(suggested if suggested and suggested.exists() else target.parent),
            QFileDialog.Option.ShowDirsOnly,
        )
        if not selected:
            return
        selected_path = Path(selected)
        if selected_path == target.parent:
            selected_path = target.parent / f"{target.name}-relic-report"
        try:
            written = export_dashboard_bundle(
                self.bundle, selected_path, self.candidates.decisions
            )
        except (ValueError, OSError) as exc:
            self.report_badge.set_status("failed", "EXPORT FAILED")
            self.report_label.setText(str(exc))
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self.report_directory = selected_path.resolve()
        self.open_button.setEnabled(True)
        self.report_badge.set_status("success", "EXPORTED")
        self.report_label.setText(
            f"Wrote {len(written)} reports to {self.report_directory}"
        )
        self.report_label.setToolTip(str(self.report_directory))
        self.view_full_report_button.setEnabled(self._full_report_path() is not None)
        self.refresh_report_history()

    @Slot()
    def open_report_folder(self) -> None:
        if self.report_directory is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.report_directory)))

    @Slot()
    def _auto_check_for_updates(self) -> None:
        self._begin_update_check(manual=False)

    @Slot()
    def check_for_updates(self) -> None:
        if self._available_update is not None:
            self._show_update_dialog()
            return
        self._begin_update_check(manual=True)

    def _begin_update_check(self, *, manual: bool) -> None:
        if self._update_check_thread is not None:
            return
        self._update_check_manual = manual
        self.update_button.setText("Checking…")
        self.update_button.setEnabled(False)
        self.update_status_label.setText("Checking the signed stable update channel…")
        self.status_message.setText("Checking the stable Relic Auditor update channel…")

        thread = QThread(self)
        worker = UpdateCheckWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._update_check_finished)
        worker.failed.connect(self._update_check_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._update_check_thread_finished)
        self._update_check_thread = thread
        self._update_check_worker = worker
        thread.start()

    @Slot(object)
    def _update_check_finished(self, manifest: UpdateManifest) -> None:
        try:
            save_update_check_state(success=True)
        except OSError:
            pass
        self.update_button.setEnabled(True)
        if manifest.is_newer_than(__version__):
            self._available_update = manifest
            self.update_button.setText(f"Update v{manifest.version}")
            self.update_button.setToolTip(
                f"Relic Auditor v{manifest.version} is ready to download and verify."
            )
            self.status_message.setText(
                f"Update available · v{__version__} → v{manifest.version}"
            )
            self.update_status_label.setText(
                f"Relic Auditor {manifest.version} is available and its manifest passed validation."
            )
            if self._update_check_manual:
                self._show_update_dialog()
            return
        self._available_update = None
        self.update_button.setText("Up to date")
        self.update_button.setToolTip("Click to check the stable channel again.")
        self.status_message.setText(f"Relic Auditor v{__version__} is up to date")
        self.update_status_label.setText(
            f"Relic Auditor {__version__} is the newest verified stable version."
        )
        if self._update_check_manual:
            QMessageBox.information(
                self,
                "Relic Auditor update",
                f"Relic Auditor v{__version__} is the newest stable version.",
            )

    @Slot(str)
    def _update_check_failed(self, message: str) -> None:
        try:
            save_update_check_state(success=False)
        except OSError:
            pass
        self.update_button.setText("Check updates")
        self.update_button.setEnabled(True)
        self._last_update_diagnostic = message
        self.update_diagnostic_label.setText(message)
        self.update_status_label.setText(
            f"Relic Auditor {__version__} is installed. Automatic updates are not available for this build yet."
        )
        self.status_message.setText("Update check unavailable · Relic remains ready offline")
        if self._update_check_manual:
            QMessageBox.warning(
                self,
                "UPDATES UNAVAILABLE",
                f"Relic Auditor {__version__} is installed.\n\n"
                "Automatic updates are not available for this build yet.",
            )

    @Slot()
    def _update_check_thread_finished(self) -> None:
        self._update_check_thread = None
        self._update_check_worker = None

    def _show_update_dialog(self) -> None:
        manifest = self._available_update
        if manifest is None:
            return
        if self._update_dialog is not None:
            self._update_dialog.raise_()
            self._update_dialog.activateWindow()
            return
        dialog = UpdateDialog(__version__, manifest, self)
        dialog.download_requested.connect(self._download_update)
        dialog.install_requested.connect(self._install_prepared_update)
        dialog.finished.connect(self._update_dialog_closed)
        self._update_dialog = dialog
        if (
            self._prepared_update is not None
            and self._prepared_update.manifest.version == manifest.version
        ):
            dialog.set_ready(self._prepared_update.installer_path)
        dialog.open()

    @Slot(int)
    def _update_dialog_closed(self, _result: int) -> None:
        self._update_dialog = None

    @Slot()
    def _download_update(self) -> None:
        manifest = self._available_update
        dialog = self._update_dialog
        if manifest is None or dialog is None or self._update_download_thread is not None:
            return
        dialog.set_downloading()
        self.status_message.setText(
            f"Downloading and verifying Relic Auditor v{manifest.version}…"
        )

        thread = QThread(self)
        worker = UpdateDownloadWorker(manifest)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(dialog.set_download_progress)
        worker.finished.connect(self._update_download_finished)
        worker.failed.connect(self._update_download_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._update_download_thread_finished)
        self._update_download_thread = thread
        self._update_download_worker = worker
        thread.start()

    @Slot(object)
    def _update_download_finished(self, prepared: PreparedUpdate) -> None:
        self._prepared_update = prepared
        self.status_message.setText(
            f"Update verified · Relic Auditor v{prepared.manifest.version} is ready"
        )
        if self._update_dialog is not None:
            self._update_dialog.set_ready(prepared.installer_path)

    @Slot(str)
    def _update_download_failed(self, message: str) -> None:
        self._prepared_update = None
        self._last_update_diagnostic = message
        self.update_diagnostic_label.setText(message)
        self.update_status_label.setText(
            "The candidate update was blocked because download or publisher verification did not pass."
        )
        self.status_message.setText("Update blocked · installer verification did not pass")
        if self._update_dialog is not None:
            self._update_dialog.set_error(
                "Relic did not run the installer because download or publisher "
                "verification failed. Technical details are available in Settings."
            )

    @Slot()
    def _update_download_thread_finished(self) -> None:
        self._update_download_thread = None
        self._update_download_worker = None

    @Slot()
    def _install_prepared_update(self) -> None:
        prepared = self._prepared_update
        if prepared is None:
            return
        if self._scan_thread is not None:
            QMessageBox.warning(
                self,
                "Audit still running",
                "Finish or cancel the current audit before installing the update.",
            )
            return
        try:
            launch_prepared_update(prepared)
        except (OSError, RuntimeError) as exc:
            self._last_update_diagnostic = f"{type(exc).__name__}: {exc}"
            self.update_diagnostic_label.setText(self._last_update_diagnostic)
            if self._update_dialog is not None:
                self._update_dialog.set_error(
                    "The verified installer could not be started. Technical details "
                    "are available in Settings."
                )
            QMessageBox.critical(
                self,
                "Update could not start",
                "The installer was not started. Relic remains on the current version.",
            )
            return
        if self._update_dialog is not None:
            self._update_dialog.accept()
        application = QApplication.instance()
        if application is not None:
            application.quit()

    def closeEvent(self, event: QCloseEvent) -> None:
        update_thread = self._update_download_thread or self._update_check_thread
        if update_thread is not None and update_thread.isRunning():
            QMessageBox.information(
                self,
                "Update task still running",
                "Wait for the current update check or verified download to finish before closing Relic.",
            )
            event.ignore()
            return
        if self._scan_thread is None:
            event.accept()
            return
        choice = QMessageBox.question(
            self,
            "Audit still running",
            "The read-only audit is still running. Close automatically when it finishes?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice == QMessageBox.StandardButton.Yes:
            self._close_when_done = True
            self.hide()
        event.ignore()


#: Keeps the window alive when the caller already owns the QApplication and we
#: return without entering an event loop; otherwise Python would collect the
#: window the moment this function returns.
_OPEN_WINDOWS: list[RelicWindow] = []


def launch_dashboard(
    initial_target: Path | None = None,
    *,
    entitlement: Entitlement | None = None,
) -> int:
    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication(sys.argv[:1])
    app.setApplicationName("Relic Auditor")
    app.setOrganizationName("Dracanus AI")
    window = RelicWindow(initial_target, entitlement=entitlement)
    _OPEN_WINDOWS.append(window)
    window.destroyed.connect(
        lambda: _OPEN_WINDOWS.remove(window) if window in _OPEN_WINDOWS else None
    )
    window.show()
    if owns_app:
        return app.exec()
    return 0
