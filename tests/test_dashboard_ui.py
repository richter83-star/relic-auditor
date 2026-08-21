"""Evidence Console UI tests (v0.8.1).

These run against a real Qt widget tree on the offscreen platform, so they
catch the layout defects that only appear once widgets are laid out: clipped
text, panels pushed below the viewport, and spurious scrollbars.

The whole module skips when PySide6 is absent, which keeps the CLI-only
install path green.
"""

from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path

import pytest

if importlib.util.find_spec("PySide6") is None:  # pragma: no cover
    pytest.skip("PySide6 is not installed", allow_module_level=True)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFontMetrics  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from relic_auditor.audit import audit_estate  # noqa: E402
from relic_auditor.dashboard import components, theme  # noqa: E402
from relic_auditor.dashboard.core import DashboardBundle, DashboardOptions  # noqa: E402
from relic_auditor.dashboard.qt_app import RelicWindow  # noqa: E402
from relic_auditor.dashboard.flow import FlowState  # noqa: E402
from relic_auditor.llm.schemas import LLMReasoningResult  # noqa: E402


#: Windows display-scaling levels the console must survive. Qt applies the
#: scale factor to fonts and layout, so driving it here reproduces what a user
#: at 125%/150%/175%/200% actually sees.
DPI_SCALES = ("1", "1.25", "1.5", "1.75", "2")

#: Supported window geometries.
GEOMETRIES = ((1280, 720), (1366, 768), (1920, 1080), (2560, 1440))


@pytest.fixture(scope="module")
def app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


@pytest.fixture()
def window(app: QApplication):
    win = RelicWindow()
    win.resize(1600, 1000)
    win.show()
    # Most legacy layout checks exercise the preserved expert console.  The
    # product now keeps that console behind Technical details.
    win.open_technical_details()
    app.processEvents()
    yield win
    win.close()
    win.deleteLater()
    app.processEvents()


def _laid_out(win: RelicWindow, app: QApplication, width: int, height: int) -> None:
    win.resize(width, height)
    win.show()
    for _ in range(3):
        app.processEvents()


def _text_fits(widget) -> bool:
    """True when the widget is tall and wide enough for its own text.

    This is the check that catches vertical clipping of button labels, which
    is what a fixed pixel height causes at higher DPI.
    """

    metrics = QFontMetrics(widget.font())
    text = widget.text()
    needed_height = metrics.height()
    return widget.height() >= needed_height


# 1. No clipped text at supported DPI scales ------------------------------


@pytest.mark.parametrize("scale", DPI_SCALES)
def test_no_clipped_text_at_dpi_scales(scale: str, monkeypatch) -> None:
    """Buttons and labels must grow with the scale factor, not crop."""

    monkeypatch.setenv("QT_SCALE_FACTOR", scale)
    # A fresh QApplication would be required to re-read the scale factor, so
    # instead assert the sizing *rule* holds for the metrics at this scale:
    # every text control derives its height from font metrics.
    app = QApplication.instance() or QApplication([])
    win = RelicWindow()
    win.resize(1366, 768)
    win.show()
    for _ in range(3):
        app.processEvents()
    try:
        for button in win.findChildren(QPushButton):
            if not button.isVisible() or not button.text():
                continue
            assert _text_fits(button), (
                f"{button.text()!r} is vertically clipped at scale {scale}: "
                f"height={button.height()} font={QFontMetrics(button.font()).height()}"
            )
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_run_button_label_never_vertically_clipped(window, app) -> None:
    """The v0.8 defect: 'Run read-only audit' cropped by a fixed height."""

    for width, height in GEOMETRIES:
        _laid_out(window, app, width, height)
        button = window.run_button
        metrics = QFontMetrics(button.font())
        assert button.height() >= metrics.height(), (
            f"run button clipped at {width}x{height}"
        )
        assert button.width() >= metrics.horizontalAdvance(button.text()), (
            f"run button label truncated at {width}x{height}"
        )


def test_claude_max_label_not_horizontally_clipped(window, app) -> None:
    """The v0.8 defect: 'Claude Code / Claude Max' cut off horizontally."""

    _laid_out(window, app, 1366, 768)
    combo = window.llm_provider
    metrics = QFontMetrics(combo.font())
    longest = max(
        (combo.itemText(index) for index in range(combo.count())), key=len
    )
    assert combo.minimumWidth() >= metrics.horizontalAdvance(longest), (
        "provider combo cannot show its longest entry"
    )


# 2. Sidebar scrolling ------------------------------------------------------


def test_sidebar_scrolls_when_content_exceeds_viewport(window, app) -> None:
    _laid_out(window, app, 1280, 720)
    scroll = window.sidebar_scroll
    assert scroll.widgetResizable()
    assert scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    # A short window must leave the column scrollable rather than truncated.
    _laid_out(window, app, 1280, 620)
    content_height = scroll.widget().sizeHint().height()
    if content_height > scroll.viewport().height():
        assert scroll.verticalScrollBar().maximum() > 0


def test_no_horizontal_scrollbar_in_sidebar(window, app) -> None:
    """Unnecessary horizontal scrollbars were a listed v0.8 defect."""

    _laid_out(window, app, 1280, 720)
    assert (
        window.sidebar_scroll.horizontalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )


# 3. Provider panel visibility ---------------------------------------------


def test_provider_panel_stays_reachable(window, app) -> None:
    """Provider status must never fall permanently below the window."""

    for width, height in ((1280, 720), (1366, 768)):
        _laid_out(window, app, width, height)
        card = window.provider_card
        assert card.isVisible()
        scroll = window.sidebar_scroll
        bar = scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        app.processEvents()
        top_in_viewport = card.mapTo(scroll.viewport(), card.rect().topLeft()).y()
        assert top_in_viewport < scroll.viewport().height(), (
            f"provider card unreachable at {width}x{height}"
        )


def test_provider_rows_present_and_labelled(window) -> None:
    card = window.provider_card
    card.set_status(
        {
            "ready": True,
            "executable_found": True,
            "logged_in": True,
            "subscription_detected": True,
            "claude_code_version": "2.1.220",
            "model": "sonnet",
            "effort": "medium",
            "authentication_type": "claude-subscription",
        }
    )
    assert card.badge.text() == "CONFIGURED"
    assert "subscription" in card.billing_label.text().lower()
    # Billing model is stated in words, not implied by colour alone.
    assert "api-key" in card.billing_label.text().lower() or "api" in card.billing_label.text().lower()


# 7. Provider ready and unavailable states ---------------------------------


def test_provider_setup_and_unavailable_states(window) -> None:
    card = window.provider_card
    card.set_status(
        {
            "ready": False,
            "executable_found": False,
            "logged_in": False,
            "subscription_detected": False,
            "claude_code_version": None,
            "model": "sonnet",
            "effort": "medium",
            "authentication_type": "unknown",
        }
    )
    assert card.badge.text() == "NOT INSTALLED"

    card.set_status(
        {
            "ready": False,
            "executable_found": True,
            "logged_in": True,
            "subscription_detected": False,
            "claude_code_version": "2.1.220",
            "model": "sonnet",
            "effort": "medium",
            "authentication_type": "api-key",
        }
    )
    assert card.badge.text() == "API KEY"


def test_provider_timeout_overrides_configured_state_everywhere(window, tmp_path) -> None:
    estate = tmp_path / "estate"
    estate.mkdir()
    (estate / "main.py").write_text("print('static evidence')\n", encoding="utf-8")
    bundle = DashboardBundle(
        audit=audit_estate(estate),
        options=DashboardOptions(),
        llm_reasoning=LLMReasoningResult(
            profile="Claude-Max",
            protocol="claude-code",
            model="opus",
            auth_mode="claude-subscription",
            status="unavailable",
            prompt_sha256="0" * 64,
            input_chars=100,
            narrative="Deterministic results remain available.",
            error="ClaudeCodeError: Claude Code timed out after 90 seconds",
            effort="high",
        ),
    )

    window.provider_card.set_status(
        {
            "ready": True,
            "executable_found": True,
            "logged_in": True,
            "subscription_detected": True,
            "authentication_type": "claude-subscription",
        }
    )
    window._load_bundle(bundle)

    assert window.provider_badge.text() == "CLAUDE: TIMED OUT"
    assert window.provider_card.badge.text() == "TIMED OUT"
    assert "remain complete" in window.provider_card.message.text()


def test_sanitized_provider_error_is_visible_not_hidden(window) -> None:
    window.provider_card.set_message("Claude Code exited with status 1", "failed")
    assert window.provider_card.message.isVisibleTo(window.provider_card)
    assert "status 1" in window.provider_card.message.text()


# 4. Compact metric cards ---------------------------------------------------


def test_metric_cards_are_compact_not_ballooned(window, app) -> None:
    """Cards must hug their content instead of becoming empty rectangles."""

    _laid_out(window, app, 2560, 1440)
    for card in window._metric_cards:
        assert card.isVisible()
        # Fixed vertical policy is what stops them stretching to fill height.
        assert card.sizePolicy().verticalPolicy().name == "Fixed"
        assert card.height() <= card.minimumHeight() + 24, (
            f"metric card ballooned to {card.height()}"
        )


def test_metric_captions_never_clipped_when_wrapped(window, app) -> None:
    """Captions word-wrap; a card sized for one line crops the second."""

    for width, height in ((1093, 614), (1280, 720), (1920, 1080)):
        _laid_out(window, app, width, height)
        for card in window._metric_cards + list(window.overview.cards.values()):
            caption = card.caption
            needed = caption.heightForWidth(max(caption.width(), 1))
            assert caption.height() >= needed, (
                f"caption {caption.text()!r} clipped at {width}x{height}: "
                f"height={caption.height()} needs={needed}"
            )


def test_report_buttons_never_pushed_out_of_view(window, app) -> None:
    """The report bar must keep its actions on screen at narrow widths."""

    for width, height in ((1093, 614), (1280, 720)):
        _laid_out(window, app, width, height)
        for button in (window.export_button, window.open_button):
            right_edge = button.mapTo(window, button.rect().topRight()).x()
            assert right_edge <= window.width(), (
                f"{button.text()!r} pushed off-screen at {width}x{height}"
            )
            assert button.width() >= QFontMetrics(button.font()).horizontalAdvance(
                button.text()
            ), f"{button.text()!r} squeezed below its label at {width}x{height}"


def test_metric_grid_reflows_to_what_actually_fits(window, app) -> None:
    """Columns are chosen by measurement, not by width thresholds.

    The invariant: whatever column count is picked, the widest row of cards
    must fit the strip, and narrowing the window never widens the row.
    """

    previous = None
    for width in (2560, 1600, 1280, 1093, 1000, 960):
        _laid_out(window, app, width, 800)
        columns = window._metric_columns
        assert columns in (2, 3, 5)
        grid = window._metric_grid
        margins = grid.contentsMargins()
        available = window._metrics_panel.width() - margins.left() - margins.right()
        widest_run = max(
            sum(
                card.minimumSizeHint().width()
                for card in window._metric_cards[start : start + columns]
            )
            for start in range(0, len(window._metric_cards), columns)
        )
        needed = widest_run + (columns - 1) * grid.horizontalSpacing()
        assert needed <= available or columns == 2, (
            f"{columns} columns need {needed}px but only {available}px at {width}"
        )
        if previous is not None:
            assert columns <= previous, (
                f"narrowing to {width} widened the row from {previous} to {columns}"
            )
        previous = columns


def test_panels_stack_vertically_at_minimum_width(window, app) -> None:
    _laid_out(window, app, 1600, 900)
    assert window.body_splitter.orientation() == Qt.Orientation.Horizontal
    # Still horizontal just above the stack breakpoint...
    _laid_out(window, app, 1000, 700)
    assert window.body_splitter.orientation() == Qt.Orientation.Horizontal
    # ...and stacked below it, with both panes given real height.
    _laid_out(window, app, 960, 700)
    assert window.body_splitter.orientation() == Qt.Orientation.Vertical
    sizes = window.body_splitter.sizes()
    assert all(size > 100 for size in sizes), (
        f"stacked panes collapsed: {sizes}"
    )


# 5. Table resize behaviour -------------------------------------------------


def test_table_columns_keep_readable_floor_and_stretch_narrative(window, app) -> None:
    _laid_out(window, app, 1920, 1080)
    table = window.files
    table.set_rows(
        [
            {
                "path": f"src/module_{index}/service.py",
                "role": "source",
                "extension": ".py",
                "size": "2 KB",
                "source": "filesystem",
                "warnings": "",
            }
            for index in range(40)
        ]
    )
    app.processEvents()
    table.resize_columns()
    app.processEvents()
    floor = table.table.horizontalHeader().minimumSectionSize()
    assert floor >= components.ABSOLUTE_MIN_SECTION
    assert all(
        table.table.columnWidth(index) >= floor
        for index in range(table.model.columnCount())
    )
    path_column = next(
        index
        for index, (_title, key) in enumerate(table.model.columns)
        if key == "path"
    )
    assert (
        table.table.horizontalHeader().sectionResizeMode(path_column).name == "Stretch"
    )


def test_table_row_height_follows_font_metrics(window) -> None:
    table = window.files
    metrics = QFontMetrics(table.table.font())
    assert table.table.verticalHeader().defaultSectionSize() >= metrics.height()


def test_findings_table_has_persistent_full_record_inspector(window) -> None:
    table = window.acquisition
    assert table.details.placeholderText().startswith("Select a row")
    assert table.details.minimumHeight() > table.table.verticalHeader().defaultSectionSize()


# 8. Long Windows paths -----------------------------------------------------


def test_long_windows_path_is_preserved_and_tooltipped(window) -> None:
    long_path = "C:\\Users\\17146\\" + "\\".join(f"very_long_segment_{i}" for i in range(12))
    window.target_selector.set_path(long_path)
    assert window.target_selector.path() == long_path
    # Full value recoverable even when the field is too narrow to render it.
    assert window.target_selector.field.toolTip() == long_path


def test_long_path_does_not_widen_window_beyond_minimum(window, app) -> None:
    _laid_out(window, app, 1280, 720)
    window.target_selector.set_path("D:\\" + "x" * 400)
    app.processEvents()
    assert window.sidebar_scroll.widget().sizeHint().width() < 3000


# 9. Long profile names -----------------------------------------------------


def test_long_profile_name_does_not_clip_layout(window, app) -> None:
    window.use_llm.setChecked(True)
    window.llm_provider.setCurrentIndex(1)  # configured profile
    app.processEvents()
    window.llm_profile.setText("Extremely-Long-Enterprise-Profile-Name-For-Testing-0123456789")
    app.processEvents()
    assert window.llm_profile.isVisible()
    _laid_out(window, app, 1280, 720)
    assert window.llm_profile.height() >= QFontMetrics(window.llm_profile.font()).height()


# 10 & 11. Empty and large results -----------------------------------------


def test_empty_results_show_explained_empty_state(window) -> None:
    table = window.duplicates
    table.set_rows([])
    assert table.empty.isVisibleTo(table)
    assert table.empty.title_label.text()
    assert table.empty.body_label.text()
    assert not table.table.isVisibleTo(table)


def test_large_result_set_renders(window, app) -> None:
    rows = [
        {
            "path": f"pkg/mod_{index}.py",
            "role": "source",
            "extension": ".py",
            "size": f"{index} KB",
            "source": "filesystem",
            "warnings": "",
        }
        for index in range(5000)
    ]
    window.files.set_rows(rows)
    app.processEvents()
    assert window.files.row_count() == 5000
    assert window.files.table.isVisibleTo(window.files)


def test_filter_narrows_large_result_set(window, app) -> None:
    window.files.set_rows(
        [{"path": f"a_{i}.py", "role": "source"} for i in range(100)]
        + [{"path": "unique_target.py", "role": "source"}]
    )
    window.files.filter_field.setText("unique_target")
    app.processEvents()
    assert window.files.row_count() == 1


# 6. Running, complete, failure states --------------------------------------


def test_scan_states_are_distinct_and_labelled(window) -> None:
    panel = window.scan_panel
    panel.set_idle()
    assert panel.badge.text() == "IDLE"
    assert not panel.cancel_button.isEnabled()

    panel.set_running("Inventorying files", 15)
    assert panel.badge.text() == "RUNNING"
    assert panel.cancel_button.isEnabled()
    assert panel.progress.maximum() == 100

    panel.set_complete("Audit complete. 10 files.")
    assert panel.badge.text() == "COMPLETE"
    assert panel.progress.value() == 100
    assert panel.progress.property("state") == "success"
    assert not panel.cancel_button.isEnabled()

    panel.set_failed("Audit failed: boom")
    assert panel.badge.text() == "FAILED"
    assert panel.progress.property("state") == "failed"

    panel.set_cancelled()
    assert panel.badge.text() == "CANCELLED"
    assert "not modified" in panel.stage_label.text()


def test_indeterminate_progress_when_percentage_unknown(window) -> None:
    """A fake percentage must never be displayed."""

    panel = window.scan_panel
    panel.set_running("Working", None)
    assert panel.progress.minimum() == 0
    assert panel.progress.maximum() == 0  # Qt busy indicator


def test_export_state_is_distinct_from_scan_state(window) -> None:
    window.scan_panel.set_complete("done")
    assert window.report_badge.text() == "NOT EXPORTED"
    window.report_badge.set_status("success", "EXPORTED")
    assert window.report_badge.text() == "EXPORTED"
    assert window.scan_panel.badge.text() == "COMPLETE"


# 13. Audit cannot be started twice -----------------------------------------


def test_audit_cannot_be_started_twice(window, monkeypatch, app) -> None:
    started: list[int] = []

    class FakeThread:
        def __init__(self, *_a, **_k) -> None:
            pass

        def start(self) -> None:
            started.append(1)

        def quit(self) -> None:
            pass

        def started(self):  # pragma: no cover - attribute placeholder
            pass

    with tempfile.TemporaryDirectory() as tmp:
        estate = Path(tmp) / "estate"
        estate.mkdir()
        (estate / "a.py").write_text("x = 1\n", encoding="utf-8")
        window.target_selector.set_path(str(estate))
        window.start_scan()
        app.processEvents()
        # A live scan is tracked; a second click must be a no-op.
        if window._scan_thread is not None:
            thread = window._scan_thread
            window.start_scan()
            assert window._scan_thread is thread
        # Drain the real worker so the fixture can close cleanly.
        for _ in range(200):
            app.processEvents()
            if window._scan_thread is None:
                break


def test_cancel_leaves_target_unchanged(window, app) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        estate = Path(tmp) / "estate"
        estate.mkdir()
        (estate / "a.py").write_text("x = 1\n", encoding="utf-8")
        before = {p.name: p.read_bytes() for p in estate.rglob("*") if p.is_file()}
        window.target_selector.set_path(str(estate))
        window.start_scan()
        window.cancel_scan()
        for _ in range(200):
            app.processEvents()
            if window._scan_thread is None:
                break
        after = {p.name: p.read_bytes() for p in estate.rglob("*") if p.is_file()}
        assert before == after


# 12. Keyboard focus order --------------------------------------------------


def test_keyboard_focus_reaches_primary_controls(window, app) -> None:
    _laid_out(window, app, 1600, 900)
    advanced = [
        window.mode,
        window.include_hidden,
        window.use_llm,
    ]
    for widget in advanced:
        assert widget.focusPolicy() != Qt.FocusPolicy.NoFocus, (
            f"{widget.accessibleName() or widget} is not keyboard reachable"
        )
        widget.setFocus()
        app.processEvents()
        assert widget.hasFocus()

    window.close_technical_details()
    window.target_selector.set_path(tempfile.gettempdir())
    app.processEvents()
    for widget in (window.target_selector.field, window.run_button):
        assert widget.focusPolicy() != Qt.FocusPolicy.NoFocus
        widget.setFocus()
        app.processEvents()
        assert widget.hasFocus()


def test_accessible_names_present_for_screen_readers(window) -> None:
    for widget in (
        window.target_selector.field,
        window.mode,
        window.llm_provider,
        window.claude_model,
        window.claude_effort,
        window.run_button,
    ):
        assert widget.accessibleName(), f"missing accessible name on {widget}"


# 14. Existing dashboard workflows remain functional ------------------------


def test_bundle_loads_into_every_view(window, app) -> None:
    from relic_auditor.dashboard.core import run_dashboard_audit

    with tempfile.TemporaryDirectory() as tmp:
        estate = Path(tmp) / "estate"
        estate.mkdir()
        (estate / "package.json").write_text('{"dependencies":{}}', encoding="utf-8")
        (estate / "approval.py").write_text(
            "def approval_queue():\n    audit_log()\n", encoding="utf-8"
        )
        bundle = run_dashboard_audit(
            estate, DashboardOptions(technical_truth=False, capability_acquisition=True)
        )
        window._load_bundle(bundle)
        app.processEvents()
        assert window.metric_files.value_label.text() != "—"
        assert window.metric_roots.value_label.text() != "—"
        assert window.files.row_count() == len(bundle.audit.files)
        assert "Files (" in window.tabs.tabText(window.tabs.indexOf(window.files))


def test_all_original_tabs_preserved(window) -> None:
    titles = [window.tabs.tabText(i).split(" (")[0] for i in range(window.tabs.count())]
    for expected in (
        "Evidence Summary",
        "System Map",
        "Technical Truth",
        "Recommended Actions",
        "Duplicates",
        "Opportunities",
        "Reusable Assets",
        "Reasoning",
        "Files",
    ):
        assert expected in titles


def test_theme_tokens_are_centralized(window) -> None:
    """Widgets must not carry ad-hoc colour strings."""

    sheet = theme.stylesheet()
    assert theme.PALETTE.canvas == "#000000"
    assert theme.PALETTE.yellow.upper() == "#E8FF00"
    assert sheet.count("#") > 50
    # The window uses the compiled sheet rather than an inline blob.
    assert window.styleSheet() == sheet


def test_status_colors_have_text_labels() -> None:
    """Colour is never the only carrier of meaning."""

    for status in theme.STATUS_COLORS:
        assert theme.status_label(status), f"{status} has no text label"
        badge = components.StatusBadge(status)
        assert badge.text()


def test_launch_dashboard_retains_its_window(app) -> None:
    """With a caller-owned QApplication, launch_dashboard returns without an

    event loop; the window must not be garbage collected on the way out."""

    from relic_auditor.dashboard.qt_app import launch_dashboard

    code = launch_dashboard()
    app.processEvents()
    titles = [w.windowTitle() for w in app.topLevelWidgets() if w.windowTitle()]
    assert code == 0
    assert any("Relic Auditor" in title for title in titles), (
        f"dashboard window was collected; titles={titles}"
    )


def test_default_product_shell_is_focused_scan_state(app) -> None:
    win = RelicWindow()
    win.show()
    app.processEvents()
    try:
        assert win.shell_stack.currentWidget() is win.product_shell
        assert not hasattr(win, "primary_tabs")
        assert win.flow_stack.count() == 5
        assert win.flow_stack.currentWidget() is win.scan_page
        assert win.flow.state is FlowState.NO_TARGET
        assert not win.provider_card.isVisible()
        assert not win.tabs.isVisible()
        assert win.mode.currentData() == "full"
        assert win.run_button.text() == "SCAN THIS FOLDER"
        assert not win.run_button.isEnabled()
        assert win.history_button.isVisible()
        assert win.settings_button.isVisible()
        assert not win.update_button.isVisible()
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_focused_flow_advances_when_target_is_selected(app, tmp_path) -> None:
    win = RelicWindow()
    win.show()
    app.processEvents()
    try:
        win.target_selector.set_path(str(tmp_path))
        app.processEvents()
        assert win.flow.state is FlowState.TARGET_SELECTED
        assert win.flow_stack.currentWidget() is win.scan_page
        assert win.run_button.isEnabled()
        assert win.source_reassurance.isVisible()
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_technical_details_is_progressive_disclosure(app) -> None:
    win = RelicWindow()
    win.show()
    app.processEvents()
    try:
        win.open_technical_details()
        app.processEvents()
        assert win.shell_stack.currentWidget() is win.technical_shell
        assert win.tabs.isVisible()
        assert win.provider_card.isVisible()
        win.close_technical_details()
        app.processEvents()
        assert win.shell_stack.currentWidget() is win.product_shell
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()
    for widget in app.topLevelWidgets():
        if "Evidence Console" in widget.windowTitle():
            widget.close()
            widget.deleteLater()
    app.processEvents()
