"""Reusable Evidence Console widgets.

Each component pulls its colours, spacing, and type from
:mod:`relic_auditor.dashboard.theme`. None of them hard-code a pixel height on
a text-bearing control: heights come from font metrics so Windows display
scaling (100%-200%) grows the control rather than clipping the glyphs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .theme import (
    PALETTE,
    RADIUS,
    SPACING,
    TYPE,
    control_height,
    status_colors,
    status_label,
)


def _apply_min_height(widget: QWidget, lines: int = 1, padding: int | None = None) -> None:
    """Give a text-bearing widget a font-derived minimum height."""

    widget.setMinimumHeight(control_height(QFontMetrics(widget.font()), lines, padding))


class RelicPanel(QFrame):
    """A titled container. The building block of every console region."""

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        parent: QWidget | None = None,
        emphasis: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("relicPanel")
        if emphasis:
            self.setProperty("emphasis", "true")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(
            SPACING.lg, SPACING.md, SPACING.lg, SPACING.lg
        )
        self._layout.setSpacing(SPACING.md)

        self.header_row = QHBoxLayout()
        self.header_row.setSpacing(SPACING.sm)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("panelTitle")
        self.title_label.setWordWrap(True)
        self.header_row.addWidget(self.title_label)
        self.header_row.addStretch(1)
        if title:
            self._layout.addLayout(self.header_row)
        if subtitle:
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setObjectName("dimLabel")
            self.subtitle_label.setWordWrap(True)
            self._layout.addWidget(self.subtitle_label)

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        self._layout.addWidget(widget, stretch)

    def add_layout(self, layout, stretch: int = 0) -> None:
        self._layout.addLayout(layout, stretch)

    def add_header_widget(self, widget: QWidget) -> None:
        self.header_row.addWidget(widget)

    def body(self) -> QVBoxLayout:
        return self._layout


class StatusBadge(QLabel):
    """A compact state chip.

    Always renders words as well as colour, so the state survives greyscale
    printing and colour-vision differences.
    """

    def __init__(self, status: str = "idle", text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusBadge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.set_status(status, text)

    def set_status(self, status: str, text: str = "") -> None:
        self._status = status
        foreground, wash, border = status_colors(status)
        label = text or status_label(status)
        self.setText(label)
        self.setStyleSheet(
            f"color: {foreground}; background: {wash};"
            f" border: 1px solid {border}; border-radius: {RADIUS.sm}px;"
            f" padding: {SPACING.xxs}px {SPACING.sm}px;"
        )
        self.setAccessibleName(f"status {label}")
        _apply_min_height(self, padding=SPACING.xxs)

    def status(self) -> str:
        return self._status


class PrimaryButton(QPushButton):
    """The single most important action in a region.

    Height is derived from font metrics, which is what keeps long labels such
    as "Run read-only audit" from being vertically clipped at 125%-200%
    Windows scaling.
    """

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("primaryButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        _apply_min_height(self, padding=SPACING.md)
        metrics = QFontMetrics(self.font())
        self.setMinimumWidth(metrics.horizontalAdvance(text) + SPACING.xxl * 2)


class SecondaryButton(QPushButton):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("secondaryButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        _apply_min_height(self)
        metrics = QFontMetrics(self.font())
        self.setMinimumWidth(metrics.horizontalAdvance(text) + SPACING.lg * 2)


class MetricCard(QFrame):
    """A compact figure plus caption.

    Deliberately sized to its content: metric cards must not become large
    empty rectangles when the console is wide.
    """

    def __init__(
        self,
        label: str,
        value: str = "0",
        tone: str = "primary",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("metricCard")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.md, SPACING.sm, SPACING.md, SPACING.sm)
        layout.setSpacing(SPACING.xxs)

        self._tone = tone
        self.value_label = QLabel()
        self.value_label.setObjectName("metricValue")
        if tone != "primary":
            self.value_label.setProperty("tone", tone)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.caption = QLabel(label.upper())
        self.caption.setObjectName("metricLabel")
        self.caption.setWordWrap(True)

        layout.addWidget(self.value_label)
        layout.addWidget(self.caption)
        self.set_value(value)
        # Reserve two caption lines. Captions word-wrap, and a card sized for a
        # single line crops the second one ("ACQUISITION FINDINGS" losing
        # "FINDINGS") once the column gets narrow.
        self.setMinimumHeight(
            control_height(QFontMetrics(self.value_label.font()), padding=SPACING.xxs)
            + control_height(QFontMetrics(self.caption.font()), lines=2, padding=0)
            + SPACING.md
        )

    #: Rendered when a figure has not been measured. A full-size em dash, not
    #: a hyphen: a small dash floating in a large card reads as a glyph that
    #: failed to render rather than as a deliberate "no data" state.
    UNAVAILABLE = "—"

    def set_value(self, value: str | None) -> None:
        """Show a measured figure, or the unavailable state.

        ``None`` and an empty string mean "not measured". Zero is never
        substituted for them: a real measured zero is a finding, and showing
        one for missing data would misstate the evidence.
        """

        unavailable = value is None or str(value).strip() in ("", self.UNAVAILABLE)
        text = self.UNAVAILABLE if unavailable else str(value)
        self.value_label.setText(text)
        self.value_label.setProperty("state", "unavailable" if unavailable else "")
        if unavailable:
            # The tone colour is for real figures; muted grey carries "no data".
            self.value_label.setProperty("tone", "")
        elif self._tone != "primary":
            self.value_label.setProperty("tone", self._tone)
        style = self.value_label.style()
        style.unpolish(self.value_label)
        style.polish(self.value_label)
        caption = self.caption.text()
        self.setAccessibleName(
            f"{caption}: not measured yet" if unavailable else f"{caption}: {text}"
        )
        self.value_label.setToolTip(
            f"{caption} has not been measured yet." if unavailable else ""
        )

    def is_unavailable(self) -> bool:
        return self.value_label.property("state") == "unavailable"


class EvidenceCard(QFrame):
    """A titled block of supporting evidence or explanation."""

    def __init__(
        self,
        title: str,
        body: str = "",
        status: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("evidenceCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
        layout.setSpacing(SPACING.sm)

        head = QHBoxLayout()
        head.setSpacing(SPACING.sm)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("panelTitle")
        self.title_label.setWordWrap(True)
        head.addWidget(self.title_label, 1)
        self.badge: StatusBadge | None = None
        if status:
            self.badge = StatusBadge(status)
            head.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(head)

        self.body_label = QLabel(body)
        self.body_label.setObjectName("mutedLabel")
        self.body_label.setWordWrap(True)
        self.body_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.body_label)

    def set_body(self, text: str) -> None:
        self.body_label.setText(text)

    def set_status(self, status: str, text: str = "") -> None:
        if self.badge is not None:
            self.badge.set_status(status, text)


class PathSelector(QWidget):
    """A labelled path field with a browse button.

    Long Windows paths stay fully readable: the field scrolls its own text and
    carries the complete path as a tooltip, so nothing is silently truncated.
    """

    path_changed = Signal(str)

    def __init__(
        self,
        label: str,
        placeholder: str = "",
        directories_only: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._directories_only = directories_only
        self._dialog_title = f"Choose {label.lower()}"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING.xs)

        caption = QLabel(label.upper())
        caption.setObjectName("sectionLabel")
        layout.addWidget(caption)

        row = QHBoxLayout()
        row.setSpacing(SPACING.sm)
        self.field = QLineEdit()
        self.field.setPlaceholderText(placeholder)
        self.field.setClearButtonEnabled(True)
        self.field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.field.setAccessibleName(label)
        _apply_min_height(self.field)
        self.field.textChanged.connect(self._on_text_changed)

        self.browse_button = SecondaryButton("Browse…")
        self.browse_button.setAccessibleName(f"Browse for {label.lower()}")
        self.browse_button.clicked.connect(self.choose)

        row.addWidget(self.field, 1)
        row.addWidget(self.browse_button, 0)
        layout.addLayout(row)

    def _on_text_changed(self, text: str) -> None:
        # The complete path is always recoverable via the tooltip even when the
        # field is too narrow to show all of it.
        self.field.setToolTip(text)
        self.path_changed.emit(text)

    def choose(self) -> None:
        current = self.field.text().strip()
        start = current or str(Path.home())
        if self._directories_only:
            selected = QFileDialog.getExistingDirectory(
                self, self._dialog_title, start, QFileDialog.Option.ShowDirsOnly
            )
        else:
            selected, _ = QFileDialog.getOpenFileName(self, self._dialog_title, start)
        if selected:
            self.field.setText(selected)

    def path(self) -> str:
        return self.field.text().strip()

    def set_path(self, value: str) -> None:
        self.field.setText(value)

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802 - Qt naming
        super().setEnabled(enabled)
        self.field.setEnabled(enabled)
        self.browse_button.setEnabled(enabled)


class ProviderStatusCard(RelicPanel):
    """Reasoning-provider setup and last-request state.

    Claude Code / Claude Max subscription billing is stated separately from
    Anthropic API-key billing so the two are never confused. Installation and
    authentication only prove that the provider is configured; ``OPERATIONAL``
    is reserved for a completed reasoning request.
    """

    check_requested = Signal()
    login_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Reasoning provider", parent=parent)
        self.badge = StatusBadge("idle", "NOT CHECKED")
        self.add_header_widget(self.badge)

        self.billing_label = QLabel(
            "Claude Code / Claude Max — subscription session, not Anthropic "
            "API-key billing."
        )
        self.billing_label.setObjectName("dimLabel")
        self.billing_label.setWordWrap(True)
        self.add_widget(self.billing_label)

        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(SPACING.md)
        self.grid.setVerticalSpacing(SPACING.xs)
        self.grid.setColumnStretch(1, 1)
        self._rows: dict[str, QLabel] = {}
        for index, (key, caption) in enumerate(
            (
                ("executable_found", "Executable"),
                ("logged_in", "Authentication"),
                ("subscription_detected", "Subscription"),
                ("claude_code_version", "Claude Code"),
                ("model", "Model"),
                ("effort", "Effort"),
            )
        ):
            name = QLabel(caption.upper())
            name.setObjectName("sectionLabel")
            value = QLabel("—")
            value.setObjectName("mutedLabel")
            value.setWordWrap(True)
            value.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.grid.addWidget(name, index, 0, Qt.AlignmentFlag.AlignTop)
            self.grid.addWidget(value, index, 1)
            self._rows[key] = value
        self.add_layout(self.grid)

        self.message = QLabel("")
        self.message.setObjectName("dimLabel")
        self.message.setWordWrap(True)
        self.message.setVisible(False)
        self.add_widget(self.message)

        # Stacked, not side by side. Each button reserves its full label width,
        # and the pair demanded ~444px on one row - enough to force the whole
        # sidebar wider than its column and clip the panel's right edge.
        actions = QVBoxLayout()
        actions.setSpacing(SPACING.sm)
        self.check_button = SecondaryButton("Check Claude setup")
        self.check_button.clicked.connect(self.check_requested.emit)
        self.login_button = SecondaryButton("Open Claude login")
        self.login_button.clicked.connect(self.login_requested.emit)
        for button in (self.check_button, self.login_button):
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            actions.addWidget(button)
        self.add_layout(actions)

    def set_status(self, status: dict[str, object]) -> None:
        def mark(value: object) -> str:
            if value is True:
                return "yes"
            if value is False:
                return "no"
            return "—" if value in (None, "") else str(value)

        self._rows["executable_found"].setText(
            "found on PATH" if status.get("executable_found") else "not found"
        )
        auth = str(status.get("authentication_type", "unknown"))
        self._rows["logged_in"].setText(
            f"signed in ({auth})" if status.get("logged_in") else f"signed out ({auth})"
        )
        self._rows["subscription_detected"].setText(
            "detected" if status.get("subscription_detected") else "not detected"
        )
        self._rows["claude_code_version"].setText(mark(status.get("claude_code_version")))
        self._rows["model"].setText(mark(status.get("model")))
        self._rows["effort"].setText(mark(status.get("effort")))

        if status.get("ready"):
            self.badge.set_status("active", "CONFIGURED")
        elif not status.get("executable_found"):
            self.badge.set_status("blocked", "NOT INSTALLED")
        elif not status.get("logged_in"):
            self.badge.set_status("warning", "SIGNED OUT")
        elif auth == "api-key":
            self.badge.set_status("warning", "API KEY")
        else:
            self.badge.set_status("warning", "UNCONFIRMED")

    def set_runtime_status(self, status: str, label: str, message: str) -> None:
        """Set the result of a real provider request.

        This deliberately overrides the setup badge. A later setup check may
        return the card to ``CONFIGURED``, but authentication alone can never
        overwrite a visible request failure with ``READY``.
        """

        self.badge.set_status(status, label)
        self.set_message(message, status)

    def set_message(self, text: str, status: str | None = None) -> None:
        """Show a sanitized provider message. Never hidden behind a dialog."""

        self.message.setText(text)
        self.message.setVisible(bool(text))
        if status:
            foreground, _, _ = status_colors(status)
            self.message.setStyleSheet(f"color: {foreground};")
        else:
            self.message.setStyleSheet("")


class ScanProgressPanel(RelicPanel):
    """Live scan state.

    Shows indeterminate motion whenever a real percentage is not available;
    it never invents a number.
    """

    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Active scan", parent=parent)
        self.badge = StatusBadge("idle")
        self.add_header_widget(self.badge)

        self.stage_label = QLabel("No scan running.")
        self.stage_label.setObjectName("mutedLabel")
        self.stage_label.setWordWrap(True)
        _apply_min_height(self.stage_label, lines=2, padding=0)
        self.add_widget(self.stage_label)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.progress.setMinimumHeight(6)
        self.progress.setMaximumHeight(8)
        self.add_widget(self.progress)

        stats = QHBoxLayout()
        stats.setSpacing(SPACING.md)
        # Short captions: these sit inside the "Active scan" panel, so the
        # context is already established, and long ones forced the sidebar
        # wider than its column at 1366x768 / 125%.
        # Unavailable, not zero. Before a scan runs nothing has been counted,
        # and "0 files / 0 roots" would assert a measurement that was never
        # taken - the same misstatement the metric placeholder rule forbids.
        self.elapsed_card = MetricCard("Elapsed", None, tone="neutral")
        self.files_card = MetricCard("Files", None, tone="evidence")
        self.roots_card = MetricCard("Roots", None, tone="evidence")
        for card in (self.elapsed_card, self.files_card, self.roots_card):
            stats.addWidget(card, 1)
        self.add_layout(stats)

        actions = QHBoxLayout()
        actions.setSpacing(SPACING.sm)
        actions.addStretch(1)
        self.cancel_button = SecondaryButton("Cancel scan")
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.setEnabled(False)
        self.cancel_button.setToolTip(
            "Stop the scan. The scanned target is read-only and stays unchanged."
        )
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        actions.addWidget(self.cancel_button)
        self.add_layout(actions)

    def set_idle(self, message: str = "No scan running.") -> None:
        self.badge.set_status("idle")
        self.stage_label.setText(message)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setProperty("state", "")
        self.cancel_button.setEnabled(False)
        # Clear stale counters back to "not measured" rather than leaving the
        # previous run's figures, or a zero, standing next to "No scan running".
        self.set_counters(None, None, None)

    def set_running(self, stage: str, percent: int | None = None) -> None:
        self.badge.set_status("running")
        self.stage_label.setText(stage)
        if percent is None:
            # Busy indicator rather than a fabricated percentage.
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(max(0, min(100, percent)))
        self.progress.setProperty("state", "")
        self._repolish()
        self.cancel_button.setEnabled(True)

    def set_complete(self, summary: str) -> None:
        self.badge.set_status("success", "COMPLETE")
        self.stage_label.setText(summary)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setProperty("state", "success")
        self._repolish()
        self.cancel_button.setEnabled(False)

    def set_failed(self, message: str) -> None:
        self.badge.set_status("failed")
        self.stage_label.setText(message)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setProperty("state", "failed")
        self._repolish()
        self.cancel_button.setEnabled(False)

    def set_cancelled(self, message: str = "Scan cancelled. The target was not modified.") -> None:
        self.badge.set_status("cancelled")
        self.stage_label.setText(message)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setProperty("state", "")
        self._repolish()
        self.cancel_button.setEnabled(False)

    def set_counters(
        self, elapsed: str | None, files: str | None, roots: str | None
    ) -> None:
        """Update the live counters. ``None`` means "not measured yet"."""

        self.elapsed_card.set_value(elapsed)
        self.files_card.set_value(files)
        self.roots_card.set_value(roots)

    def _repolish(self) -> None:
        style = self.progress.style()
        style.unpolish(self.progress)
        style.polish(self.progress)


class EmptyState(QWidget):
    """Explains why a region is blank. No unexplained empty panels.

    ``marker`` draws a small muted glyph above the heading so the block reads
    as a designed state rather than a void. ``compact`` trims the padding for
    side panels that must not be dominated by their own empty state.
    """

    #: Evidence-oriented marker. Deliberately a plain glyph, not an icon file,
    #: so it inherits the theme colour and scales with the system font.
    EVIDENCE_MARKER = "⌕"

    def __init__(
        self,
        title: str,
        body: str = "",
        parent: QWidget | None = None,
        marker: str | None = None,
        compact: bool = False,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        pad = SPACING.md if compact else SPACING.xl
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(SPACING.xs if compact else SPACING.sm)
        self._compact = compact
        if compact:
            # A compact notice sizes to its text so it cannot dominate a panel.
            policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        else:
            layout.addStretch(1)
            policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        # Wrapped text is taller at narrow widths than a plain sizeHint says.
        # Without height-for-width the last line of the explanation is cropped.
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

        self.marker_label = QLabel(marker or "")
        self.marker_label.setObjectName("emptyMarker")
        self.marker_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.marker_label.setVisible(bool(marker))

        self.title_label = QLabel(title)
        self.title_label.setObjectName("emptyTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setWordWrap(True)

        self.body_label = QLabel(body)
        self.body_label.setObjectName("emptyBody")
        self.body_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body_label.setWordWrap(True)

        layout.addWidget(self.marker_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.body_label)
        layout.addStretch(1)

    def set_text(self, title: str, body: str = "") -> None:
        self.title_label.setText(title)
        self.body_label.setText(body)
        self.updateGeometry()

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt naming
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt naming
        """Height needed once the title and body wrap at ``width``."""

        layout = self.layout()
        margins = layout.contentsMargins()
        inner = max(1, width - margins.left() - margins.right())
        heights = []
        if self.marker_label.isVisible() and self.marker_label.text():
            heights.append(self.marker_label.sizeHint().height())
        for label in (self.title_label, self.body_label):
            if label.text():
                heights.append(label.heightForWidth(inner))
        if not heights:
            return margins.top() + margins.bottom()
        return (
            margins.top()
            + margins.bottom()
            + sum(heights)
            + layout.spacing() * (len(heights) - 1)
        )

    def sizeHint(self):  # noqa: N802 - Qt naming
        hint = super().sizeHint()
        hint.setHeight(max(hint.height(), self.heightForWidth(max(hint.width(), 1))))
        return hint

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        # Parent layouts allocate from sizeHint, which is measured at the hint
        # width rather than the real one. Claim the height the text actually
        # needs at the width we were given, so the last line is never cropped.
        needed = self.heightForWidth(max(self.width(), 1))
        if self.minimumHeight() != needed:
            self.setMinimumHeight(needed)

    def minimumSizeHint(self):  # noqa: N802 - Qt naming
        return self.sizeHint() if self._compact else super().minimumSizeHint()


class FindingsTable(QWidget):
    """A filterable evidence table with a persistent full-detail inspector.

    The grid is an index, not the only way to recover a record. Columns retain
    readable widths and technical grids may scroll horizontally; selecting a
    row always exposes the complete structured record below the grid.
    """

    selection_changed = Signal(list)

    def __init__(
        self,
        columns: Iterable[tuple[str, str]],
        placeholder: str = "Filter…",
        empty_title: str = "No rows yet",
        empty_body: str = "Run an audit to populate this view.",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        from .widgets import RecordTableModel  # local import avoids a cycle

        self._columns = list(columns)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING.sm)

        self.filter_field = QLineEdit()
        self.filter_field.setPlaceholderText(placeholder)
        self.filter_field.setClearButtonEnabled(True)
        self.filter_field.setAccessibleName(placeholder)
        _apply_min_height(self.filter_field)
        self.filter_field.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter_field)

        self.model = RecordTableModel(self._columns)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().setVisible(False)
        self.table.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        header = self.table.horizontalHeader()
        # Widths are computed explicitly in resize_columns; letting Qt stretch
        # the last section as well would fight that arithmetic.
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(readable_min_section(self.table))
        header.setHighlightSections(False)

        # Rows sized from the font, so text is never vertically cropped.
        row_height = control_height(
            QFontMetrics(self.table.font()), padding=SPACING.md
        )
        self.table.verticalHeader().setDefaultSectionSize(row_height)

        self.table.selectionModel().selectionChanged.connect(self._selection_changed)

        self.empty = EmptyState(empty_title, empty_body)
        table_stack = QWidget()
        stack_layout = QVBoxLayout(table_stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)
        stack_layout.setSpacing(0)
        stack_layout.addWidget(self.table)
        stack_layout.addWidget(self.empty)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText(
            "Select a row to view the complete, untruncated record."
        )
        self.details.setAccessibleName("Selected record details")
        self.details.setMaximumBlockCount(5_000)
        self.details.setMinimumHeight(
            control_height(QFontMetrics(self.details.font()), lines=6, padding=SPACING.sm)
        )

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(table_stack)
        self.splitter.addWidget(self.details)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 2)
        layout.addWidget(self.splitter, 1)
        self._show_empty(True)

    def _show_empty(self, empty: bool) -> None:
        self.empty.setVisible(empty)
        self.table.setVisible(not empty)

    def set_rows(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.details.clear()
        self._apply_filter(self.filter_field.text())

    def _apply_filter(self, text: str) -> None:
        rows = getattr(self, "_rows", [])
        needle = text.strip().lower()
        if needle:
            rows = [
                row
                for row in rows
                if needle in " ".join(str(value).lower() for value in row.values())
            ]
        self.model.set_rows(rows)
        self._show_empty(not rows)
        if rows:
            self.resize_columns()

    def resize_columns(self) -> None:
        """Fit columns to the viewport. Shared with the legacy record table."""

        fit_table_columns(self.table, self.model.columnCount())

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        if self.table.isVisible() and self.model.rowCount():
            self.resize_columns()

    def selected_rows(self) -> list[dict[str, object]]:
        indexes = self.table.selectionModel().selectedRows()
        rows = []
        for index in indexes:
            row = self.model.row_at(index.row())
            if row is not None:
                rows.append(row)
        return rows

    def _selection_changed(self) -> None:
        rows = self.selected_rows()
        if rows:
            raw = rows[0].get("_raw", rows[0])
            self.details.setPlainText(
                json.dumps(raw, indent=2, sort_keys=True, default=str)
            )
        else:
            self.details.clear()
        self.selection_changed.emit(rows)

    def row_count(self) -> int:
        return self.model.rowCount()


class ElidedLabel(QLabel):
    """Single-line label that elides instead of wrapping or demanding width.

    Used where a status sentence shares a row with buttons: wrapping would
    make the row grow tall, and demanding the full width would push the
    buttons off-screen. The complete text is always available as a tooltip.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = text
        self.setWordWrap(False)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        self._full_text = text
        self.setToolTip(text)
        self._apply_elide()

    def full_text(self) -> str:
        return self._full_text

    def _apply_elide(self) -> None:
        metrics = QFontMetrics(self.font())
        available = max(0, self.width())
        if available <= 0:
            super().setText(self._full_text)
            return
        super().setText(
            metrics.elidedText(self._full_text, Qt.TextElideMode.ElideRight, available)
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._apply_elide()


#: Hard floor for a column. Technical data is allowed to scroll horizontally
#: rather than compress below this point.
ABSOLUTE_MIN_SECTION = 72

#: Where a table remembers its unshrunken column floor, so repeated fits at
#: narrow widths cannot permanently ratchet it down.
_BASE_MIN_SECTION_PROPERTY = "relicBaseMinSection"


def readable_min_section(table: QTableView) -> int:
    """A column floor based on average glyph width.

    Using the widest glyph ("M") would make the floor so wide that several
    columns could never fit a normal viewport, forcing a permanent horizontal
    scrollbar.
    """

    return max(ABSOLUTE_MIN_SECTION, QFontMetrics(table.font()).averageCharWidth() * 11)


def fit_table_columns(table: QTableView, column_count: int) -> None:
    """Size a technical table for reading rather than maximum column count.

    Short fields keep content-aware widths, the most useful narrative field
    consumes remaining space, and narrow viewports receive an honest
    horizontal scrollbar. The old proportional fitter squeezed seven-column
    records to roughly 44 pixels each, leaving only ellipses.
    """

    if column_count <= 0:
        return
    header = table.horizontalHeader()
    base_min = table.property(_BASE_MIN_SECTION_PROPERTY)
    if not isinstance(base_min, int) or base_min <= 0:
        base_min = readable_min_section(table)
        table.setProperty(_BASE_MIN_SECTION_PROPERTY, base_min)
    header.setMinimumSectionSize(base_min)
    for index in range(column_count):
        header.setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
    table.resizeColumnsToContents()

    model = table.model()
    if hasattr(model, "sourceModel"):
        model = model.sourceModel()
    columns = getattr(model, "columns", [])
    keys = [str(item[1]) for item in columns] if columns else []
    narrative_priority = (
        "summary",
        "content",
        "evidence",
        "appraisal_reasons",
        "paths",
        "path",
        "warnings",
    )
    narrative = next(
        (keys.index(key) for key in narrative_priority if key in keys),
        column_count - 1,
    )

    maximum_short = base_min * 3
    short_columns = [index for index in range(column_count) if index != narrative]
    desired = {
        index: max(base_min, min(table.columnWidth(index), maximum_short))
        for index in short_columns
    }
    viewport_width = max(0, table.viewport().width())
    minimum_total = base_min * column_count
    if viewport_width >= minimum_total:
        # Preserve the readable floor, but share only the space that remains
        # after reserving one floor-width for the narrative column. This keeps
        # ordinary records inside a normal viewport without reviving the old
        # 44-pixel squeeze.
        extra_budget = viewport_width - minimum_total
        desired_extra = sum(width - base_min for width in desired.values())
        scale = min(1.0, extra_budget / desired_extra) if desired_extra else 1.0
        desired = {
            index: base_min + int((width - base_min) * scale)
            for index, width in desired.items()
        }
    else:
        # The readable minima do not fit. Use an honest horizontal scrollbar
        # instead of compressing any field below the floor.
        desired = {index: base_min for index in short_columns}
    for index, width in desired.items():
        table.setColumnWidth(index, width)
    narrative_width = (
        max(base_min, viewport_width - sum(desired.values()))
        if viewport_width >= minimum_total
        else base_min
    )
    # On Windows, changing a content-sized section directly to Stretch can
    # preserve its old width until a later layout pass. Seed the intended
    # remainder first so the current frame is correct as well.
    table.setColumnWidth(narrative, narrative_width)
    header.setSectionResizeMode(narrative, QHeaderView.ResizeMode.Stretch)


def hairline(parent: QWidget | None = None) -> QFrame:
    """A one-pixel divider that follows the token border colour."""

    line = QFrame(parent)
    line.setObjectName("hairline")
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return line


def section_label(text: str, parent: QWidget | None = None) -> QLabel:
    label = QLabel(text.upper(), parent)
    label.setObjectName("sectionLabel")
    label.setWordWrap(True)
    return label
