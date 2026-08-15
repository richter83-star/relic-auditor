"""Visual-polish regression tests for the Evidence Console (v0.8.1).

Each test here pins one of the six corrections made in the polish pass, so a
future layout or theme change cannot quietly reintroduce the defect.
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
from PySide6.QtGui import QFontMetrics, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from relic_auditor.dashboard import components, theme  # noqa: E402
from relic_auditor.dashboard.core import DashboardOptions, run_dashboard_audit  # noqa: E402
from relic_auditor.dashboard.qt_app import RelicWindow  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(app: QApplication):
    win = RelicWindow()
    win.resize(1600, 1000)
    win.show()
    for _ in range(3):
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


# 1. Cancel scan state ------------------------------------------------------


def test_cancel_disabled_while_idle(window) -> None:
    window.scan_panel.set_idle()
    assert not window.scan_panel.cancel_button.isEnabled()


def test_cancel_enabled_only_during_active_scan(window) -> None:
    panel = window.scan_panel
    panel.set_idle()
    assert not panel.cancel_button.isEnabled()
    panel.set_running("Inventorying files", 10)
    assert panel.cancel_button.isEnabled(), "cancel must be usable while running"


@pytest.mark.parametrize(
    "terminal",
    ["complete", "failed", "cancelled", "idle"],
)
def test_cancel_disabled_after_every_terminal_state(window, terminal: str) -> None:
    panel = window.scan_panel
    panel.set_running("Working", None)
    assert panel.cancel_button.isEnabled()
    {
        "complete": lambda: panel.set_complete("done"),
        "failed": lambda: panel.set_failed("boom"),
        "cancelled": panel.set_cancelled,
        "idle": panel.set_idle,
    }[terminal]()
    assert not panel.cancel_button.isEnabled(), (
        f"cancel still enabled after {terminal}"
    )


def test_disabled_cancel_is_visually_distinct(window) -> None:
    """An ID selector outranks :disabled, so the disabled rule must exist.

    Without it a disabled Cancel button still painted in live red and read as
    clickable.
    """

    sheet = theme.stylesheet()
    assert "QPushButton#dangerButton:disabled" in sheet
    disabled_block = sheet.split("QPushButton#dangerButton:disabled")[1].split("}")[0]
    assert theme.PALETTE.text_dim in disabled_block
    assert theme.PALETTE.red not in disabled_block


def test_cancel_still_stops_a_running_scan_safely(window, app) -> None:
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
        assert not window.scan_panel.cancel_button.isEnabled()


# 2. Pivot suggestions empty state -----------------------------------------


def test_pivot_panel_shows_empty_state_not_a_void(window) -> None:
    overview = window.overview
    assert overview.pivots_empty.isVisibleTo(overview)
    assert not overview.pivots.isVisibleTo(overview)
    assert overview.pivots_empty.title_label.text() == "No pivot evidence yet"
    body = overview.pivots_empty.body_label.text().lower()
    assert "audit" in body and "opportunit" in body
    assert overview.pivots_empty.marker_label.text() == components.EmptyState.EVIDENCE_MARKER
    assert overview.pivots_empty.marker_label.isVisibleTo(overview)


def test_pivot_empty_state_invents_no_findings(window) -> None:
    """Nothing in the empty state may look like a real suggestion."""

    text = " ".join(
        (
            window.overview.pivots_empty.title_label.text(),
            window.overview.pivots_empty.body_label.text(),
        )
    ).lower()
    for fabricated in ("confidence:", "evidence:", "score", "example", "sample"):
        assert fabricated not in text
    assert window.overview.pivots.count() == 0


def test_pivot_empty_state_stays_compact(window, app) -> None:
    _laid_out(window, app, 1920, 1080)
    empty = window.overview.pivots_empty
    assert empty.height() < window.height() // 2, "empty state dominates the page"


def test_empty_state_text_is_never_cropped(window, app) -> None:
    """Wrapped explanations must get the height they actually need."""

    for width, height in ((1093, 614), (1280, 720), (1920, 1080)):
        _laid_out(window, app, width, height)
        for empty in (window.overview.pivots_empty, window.overview.projects.empty):
            needed = empty.heightForWidth(max(empty.width(), 1))
            assert empty.height() >= needed, (
                f"empty state cropped at {width}x{height}: "
                f"{empty.height()} < {needed}"
            )
            assert empty.hasHeightForWidth()


def test_pivot_panel_switches_to_list_when_evidence_exists(window, app) -> None:
    overview = window.overview
    overview.pivots.addItem("Some deterministic pivot")
    overview.set_pivots_empty(False)
    app.processEvents()
    assert overview.pivots.isVisibleTo(overview)
    assert not overview.pivots_empty.isVisibleTo(overview)


def test_pivot_empty_state_wording_differs_after_a_scan(window) -> None:
    window.overview.set_pivots_empty(True, scanned=True)
    assert window.overview.pivots_empty.title_label.text() == "No pivot evidence found"
    window.overview.set_pivots_empty(True, scanned=False)
    assert window.overview.pivots_empty.title_label.text() == "No pivot evidence yet"


# 3. Table scrollbars -------------------------------------------------------


def test_empty_table_has_no_horizontal_scrollbar(window, app) -> None:
    table = window.overview.projects
    table.set_rows([])
    app.processEvents()
    assert not table.table.isVisibleTo(table), "empty grid should not be shown"
    assert not table.table.horizontalScrollBar().isVisible()
    assert table.empty.isVisibleTo(table)


def _project_rows(count: int, text: str = "src/app/service") -> list[dict]:
    return [
        {
            "root": text,
            "kinds": "python",
            "appraisal_score": 80,
            "appraisal_category": "keep",
            "source_files": 12,
            "test_files": 3,
            "appraisal_reasons": "has tests and entrypoints",
        }
        for _ in range(count)
    ]


def test_normal_table_content_fits_without_scrollbar(window, app) -> None:
    _laid_out(window, app, 1600, 1000)
    table = window.overview.projects
    table.set_rows(_project_rows(8))
    for _ in range(3):
        app.processEvents()
    total = sum(
        table.table.columnWidth(i) for i in range(table.model.columnCount())
    )
    assert total <= table.table.viewport().width() + 4
    assert not table.table.horizontalScrollBar().isVisible()


def test_long_values_elide_with_tooltips(window, app) -> None:
    _laid_out(window, app, 1600, 1000)
    table = window.overview.projects
    table.set_rows(_project_rows(3, text="X" * 400))
    for _ in range(3):
        app.processEvents()
    total = sum(
        table.table.columnWidth(i) for i in range(table.model.columnCount())
    )
    assert total <= table.table.viewport().width() + 4
    assert table.table.textElideMode() == Qt.TextElideMode.ElideRight
    tooltip = table.model.data(table.model.index(0, 0), Qt.ItemDataRole.ToolTipRole)
    assert tooltip and "X" * 50 in tooltip, "full value must survive on the tooltip"


def test_table_imposes_no_large_workspace_minimum(window, app) -> None:
    _laid_out(window, app, 1600, 1000)
    table = window.overview.projects
    table.set_rows(_project_rows(5))
    app.processEvents()
    assert table.table.minimumWidth() == 0
    assert window.overview.minimumSizeHint().width() < 900


def test_large_result_set_remains_usable(window, app) -> None:
    _laid_out(window, app, 1600, 1000)
    table = window.overview.projects
    table.set_rows(_project_rows(3000))
    for _ in range(3):
        app.processEvents()
    assert table.model.rowCount() == 3000
    assert table.table.isVisibleTo(table)
    assert not table.table.horizontalScrollBar().isVisible()


# 4. Metric placeholders ----------------------------------------------------


def test_metric_unavailable_uses_em_dash_not_zero(window) -> None:
    card = window.metric_files
    card.set_value(None)
    assert card.value_label.text() == components.MetricCard.UNAVAILABLE
    assert card.value_label.text() == "—"
    assert card.is_unavailable()
    assert "not measured" in card.accessibleName().lower()


def test_metric_zero_is_a_real_measurement(window) -> None:
    card = window.metric_roots
    card.set_value("0")
    assert card.value_label.text() == "0"
    assert not card.is_unavailable(), "a measured zero must not read as missing"
    assert card.value_label.property("state") != "unavailable"


def test_metric_populated_uses_value_hierarchy(window) -> None:
    card = window.metric_acquisition
    card.set_value("1,234")
    assert card.value_label.text() == "1,234"
    assert not card.is_unavailable()
    assert card.value_label.property("tone") == "evidence"
    assert card.value_label.objectName() == "metricValue"


def test_metric_placeholder_is_proportional_and_muted(window) -> None:
    card = window.metric_files
    card.set_value(None)
    metrics = QFontMetrics(card.value_label.font())
    caption_metrics = QFontMetrics(card.caption.font())
    # Rendered in the metric value type, not shrunk to caption size, and at
    # least as wide as a digit would be - not a tiny stray dash.
    assert metrics.horizontalAdvance("—") >= metrics.horizontalAdvance("0")
    assert metrics.height() > caption_metrics.height()
    assert card.value_label.height() >= metrics.height()
    # It occupies the value slot rather than floating in an oversized card.
    assert card.value_label.height() <= card.height()
    # The rendered colour, not just the rule text. set_value flips a dynamic
    # property AND re-polishes; without the re-polish the em dash keeps the
    # previous tone colour and still reads as a live measured figure.
    def rendered(label) -> str:
        return label.palette().color(QPalette.ColorRole.WindowText).name().lower()

    card.set_value(None)
    assert rendered(card.value_label) == theme.PALETTE.text_dim.lower(), (
        "unavailable placeholder is not painted in the muted colour"
    )
    card.set_value("7")
    assert rendered(card.value_label) != theme.PALETTE.text_dim.lower(), (
        "a measured figure must not stay muted"
    )
    card.set_value(None)
    assert rendered(card.value_label) == theme.PALETTE.text_dim.lower(), (
        "returning to unavailable must re-mute the value"
    )


def test_metric_label_and_placeholder_are_associated(window) -> None:
    card = window.metric_candidates
    card.set_value(None)
    assert card.caption.text() in card.accessibleName()
    assert card.caption.text().lower() in card.value_label.toolTip().lower()


# 5. Label background bands -------------------------------------------------


def test_ordinary_labels_have_transparent_background(window) -> None:
    """Ordinary captions must sit on their panel, not on a black band."""

    sheet = theme.stylesheet()
    # The GLOBAL rule specifically. A substring probe for "QLabel {" is also
    # satisfied by "QStatusBar QLabel { ... }", so it would pass with the fix
    # removed entirely.
    global_rules = [
        line.strip()
        for line in sheet.splitlines()
        if line.strip().startswith("QLabel {")
    ]
    assert global_rules, "no global QLabel rule; label bands would return"
    assert "background: transparent" in global_rules[0]
    banded = []
    for label in window.findChildren(QLabel):
        name = label.objectName()
        if name in ("statusBadge",):
            continue  # badges deliberately carry their own wash
        inline = label.styleSheet()
        if "background" in inline and "transparent" not in inline:
            banded.append(name or label.text()[:24])
    assert not banded, f"labels carrying an explicit background: {banded}"


def test_section_labels_do_not_paint_their_own_background(window) -> None:
    sheet = theme.stylesheet()
    block = sheet.split("QLabel#sectionLabel")[1].split("}")[0]
    assert "background" not in block, (
        "section captions must inherit the panel surface"
    )


def test_inputs_remain_visually_distinct_from_panels(window) -> None:
    """Removing label bands must not flatten the input fields."""

    sheet = theme.stylesheet()
    input_block = sheet.split("QLineEdit, QComboBox, QPlainTextEdit, QSpinBox")[1].split("}")[0]
    assert theme.PALETTE.inset in input_block
    assert theme.PALETTE.inset != theme.PALETTE.panel


def test_contrast_of_muted_text_on_panel_is_readable() -> None:
    """WCAG contrast for the dimmest body text against its panel."""

    def luminance(hex_color: str) -> float:
        value = hex_color.lstrip("#")
        channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [
            c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
            for c in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def ratio(a: str, b: str) -> float:
        la, lb = luminance(a), luminance(b)
        lighter, darker = max(la, lb), min(la, lb)
        return (lighter + 0.05) / (darker + 0.05)

    palette = theme.PALETTE
    # Every body colour, against BOTH surfaces text sits on. Captions are 7pt,
    # so the small-text 4.5:1 floor applies - not the 3.0 large-text floor.
    # Checking only `panel` would miss metric captions, which render on the
    # lifted `panel_raised` card surface where contrast is lower.
    for surface in (palette.panel, palette.panel_raised, palette.canvas):
        assert ratio(palette.text, surface) >= 4.5, f"text on {surface}"
        assert ratio(palette.text_muted, surface) >= 4.5, f"muted on {surface}"
        assert ratio(palette.text_dim, surface) >= 4.5, (
            f"dim caption text on {surface} is "
            f"{ratio(palette.text_dim, surface):.3f}:1, below the 4.5 AA floor"
        )


# 6. Bottom status line -----------------------------------------------------


def test_status_line_not_vertically_clipped(window, app) -> None:
    for width, height in ((1280, 720), (1366, 768), (1920, 1080), (2560, 1440)):
        _laid_out(window, app, width, height)
        label = window.status_message
        metrics = QFontMetrics(label.font())
        assert label.height() >= metrics.height() + metrics.descent(), (
            f"status text clipped at {width}x{height}: "
            f"{label.height()} < {metrics.height() + metrics.descent()}"
        )
        assert window.statusBar().height() >= label.height()


def test_status_line_does_not_waste_vertical_space(window, app) -> None:
    _laid_out(window, app, 1920, 1080)
    metrics = QFontMetrics(window.status_message.font())
    assert window.statusBar().height() <= metrics.height() * 3 + 12


def test_long_status_message_elides_with_tooltip(window, app) -> None:
    _laid_out(window, app, 1280, 720)
    long_message = "Local-first · " + "extremely detailed status detail · " * 20
    window.status_message.setText(long_message)
    app.processEvents()
    assert window.status_message.full_text() == long_message
    assert window.status_message.toolTip() == long_message
    # The displayed text must actually be shortened, not merely stored.
    shown = window.status_message.text()
    assert shown != long_message, "status message was not elided"
    assert len(shown) < len(long_message)
    assert QFontMetrics(window.status_message.font()).horizontalAdvance(shown) <= (
        window.status_message.width() + 4
    )
    assert window.status_message.width() <= window.width()


def test_status_line_is_font_metric_driven_not_fixed(window, app) -> None:
    """Height must follow the font, not a hard-coded pixel value."""

    label = window.status_message
    metrics = QFontMetrics(label.font())
    assert label.minimumHeight() >= metrics.height()
    assert label.maximumHeight() > metrics.height() * 4  # no rigid cap


# Preserved behaviour -------------------------------------------------------


def test_polish_preserves_evidence_console_identity(window) -> None:
    palette = theme.PALETTE
    assert palette.canvas == "#000000"
    assert palette.yellow.upper() == "#E8FF00"
    assert window.styleSheet() == theme.stylesheet()
    assert window.run_button.objectName() == "primaryButton"


def test_polish_preserves_bundle_loading(window, app) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        estate = Path(tmp) / "estate"
        estate.mkdir()
        (estate / "package.json").write_text('{"dependencies":{}}', encoding="utf-8")
        (estate / "approval.py").write_text(
            "def approval_queue():\n    audit_log()\n", encoding="utf-8"
        )
        bundle = run_dashboard_audit(
            estate,
            DashboardOptions(technical_truth=False, capability_acquisition=True),
        )
        window._load_bundle(bundle)
        app.processEvents()
        assert not window.metric_files.is_unavailable()
        assert window.metric_files.value_label.text() != "—"
        # Pivot panel resolves to one state or the other, never both.
        overview = window.overview
        assert overview.pivots.isVisibleTo(overview) != overview.pivots_empty.isVisibleTo(overview)


# Defects found by the adversarial review of this polish pass ---------------


def test_cancel_button_keeps_the_object_name_its_styling_depends_on(window) -> None:
    """The disabled rule matches on #dangerButton; pin the name."""

    assert window.scan_panel.cancel_button.objectName() == "dangerButton"


def test_column_floor_does_not_ratchet_down_permanently(window, app) -> None:
    """A narrow layout must never trade readable cells for fewer scrollbars."""

    table = window.files
    rows = [
        {
            "path": f"src/module_{i}/service.py",
            "role": "source",
            "extension": ".py",
            "size": "2 KB",
            "source": "filesystem",
            "warnings": "",
        }
        for i in range(20)
    ]
    _laid_out(window, app, 2560, 1440)
    table.set_rows(rows)
    app.processEvents()
    table.resize_columns()
    wide_floor = table.table.horizontalHeader().minimumSectionSize()

    _laid_out(window, app, 1000, 700)
    table.resize_columns()
    app.processEvents()

    _laid_out(window, app, 2560, 1440)
    table.resize_columns()
    app.processEvents()
    recovered = table.table.horizontalHeader().minimumSectionSize()
    assert recovered == wide_floor
    assert recovered >= components.ABSOLUTE_MIN_SECTION


def test_active_scan_counters_start_unmeasured_not_zero(window) -> None:
    """"No scan running" must not sit above a fabricated 0 files / 0 roots."""

    panel = window.scan_panel
    panel.set_idle()
    for card in (panel.elapsed_card, panel.files_card, panel.roots_card):
        assert card.is_unavailable(), f"{card.caption.text()} shows a fake figure"
        assert card.value_label.text() == components.MetricCard.UNAVAILABLE


def test_scan_counters_clear_between_runs(window) -> None:
    """A finished run's figures must not linger next to an idle panel."""

    panel = window.scan_panel
    panel.set_counters("12s", "431", "7")
    assert panel.files_card.value_label.text() == "431"
    panel.set_idle()
    assert panel.files_card.is_unavailable()
    assert panel.roots_card.is_unavailable()


def test_measured_zero_still_renders_in_scan_counters(window) -> None:
    """Clearing to unavailable must not swallow a genuine zero result."""

    panel = window.scan_panel
    panel.set_counters("3s", "0", "0")
    assert panel.files_card.value_label.text() == "0"
    assert not panel.files_card.is_unavailable()
