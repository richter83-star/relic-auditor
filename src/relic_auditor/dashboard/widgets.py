from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .components import EmptyState as _EmptyState
from .components import MetricCard as _ThemedMetricCard
from .components import fit_table_columns as _fit_table_columns
from .components import readable_min_section as _readable_min_section
from .core import DashboardBundle, candidate_key
from .theme import SPACING, control_height


def public_record(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "public"):
        return value.public()
    if is_dataclass(value):
        return asdict(value)
    return {"value": str(value)}


class RecordTableModel(QAbstractTableModel):
    def __init__(
        self,
        columns: list[tuple[str, str]],
        rows: list[dict[str, Any]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.columns = columns
        self.rows = rows or []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self.rows):
            return None
        row = self.rows[index.row()]
        key = self.columns[index.column()][1]
        value = row.get(key)
        if role == Qt.ItemDataRole.DisplayRole:
            return _display(value)
        if role == Qt.ItemDataRole.EditRole:
            return value if isinstance(value, (int, float)) else _display(value)
        if role == Qt.ItemDataRole.UserRole:
            return row
        if role == Qt.ItemDataRole.ToolTipRole:
            # Columns elide when a value cannot fit; the full value must stay
            # recoverable rather than being silently truncated.
            text = _full_display(value)
            return text if text else None
        if role == Qt.ItemDataRole.TextAlignmentRole and isinstance(value, (int, float)):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole:
            if key in {"score", "appraisal_score", "overall_score"} and isinstance(value, int):
                if value >= 75:
                    return QColor("#58d6a2")
                if value < 40:
                    return QColor("#f0a273")
            if key == "decision" and value:
                return QColor("#e7bf73")
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.columns[section][0]
        return None

    def sort(self, column: int, order: Qt.SortOrder) -> None:
        if not 0 <= column < len(self.columns):
            return
        key = self.columns[column][1]
        reverse = order == Qt.SortOrder.DescendingOrder
        self.layoutAboutToBeChanged.emit()
        self.rows.sort(
            key=lambda row: _sort_value(row.get(key)),
            reverse=reverse,
        )
        self.layoutChanged.emit()

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def row_at(self, row: int) -> dict[str, Any] | None:
        if 0 <= row < len(self.rows):
            return self.rows[row]
        return None


class RecordTable(QWidget):
    row_selected = Signal(object)

    def __init__(
        self,
        columns: list[tuple[str, str]],
        *,
        placeholder: str = "Filter results…",
        multi_select: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.model = RecordTableModel(columns, parent=self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setSortRole(Qt.ItemDataRole.EditRole)

        self.search = QLineEdit()
        self.search.setPlaceholderText(placeholder)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.proxy.setFilterFixedString)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QTableView.SelectionMode.ExtendedSelection
            if multi_select
            else QTableView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        # Long values elide (with the full text on the tooltip) instead of
        # widening the table past its viewport and raising a horizontal
        # scrollbar.
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(_readable_min_section(self.table))
        header.setHighlightSections(False)
        self.table.setHorizontalScrollMode(QTableView.ScrollMode.ScrollPerPixel)
        self.table.verticalHeader().setDefaultSectionSize(
            control_height(self.table.fontMetrics(), padding=SPACING.md)
        )
        # The table must not impose a large minimum width on the workspace.
        self.table.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
        )
        self.table.setMinimumWidth(0)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Select a row to inspect its evidence.")
        self.details.setMaximumBlockCount(5_000)
        self.details.setMinimumHeight(
            control_height(self.details.fontMetrics(), lines=6, padding=SPACING.sm)
        )

        # A bare table with no rows reads as a broken panel. Swap in a stated
        # reason instead of leaving an unexplained blank grid.
        self.empty = _EmptyState(
            "Nothing to show yet",
            "Run a read-only audit, or adjust the filter above.",
        )

        table_stack = QWidget()
        stack_layout = QVBoxLayout(table_stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)
        stack_layout.setSpacing(0)
        stack_layout.addWidget(self.table)
        stack_layout.addWidget(self.empty)

        # Correct initial state: without this both the grid and its empty
        # state were visible at construction, and the unpopulated grid raised
        # a horizontal scrollbar under an otherwise blank panel.
        self.set_empty_state(True)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(table_stack)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.search)
        layout.addWidget(splitter)

        self.table.selectionModel().selectionChanged.connect(self._selection_changed)

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self.model.set_rows(rows)
        self.details.clear()
        self.set_empty_state(not rows)
        if rows:
            self.fit_columns()

    def fit_columns(self) -> None:
        _fit_table_columns(self.table, self.model.columnCount())

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        if self.table.isVisible() and self.model.rowCount():
            self.fit_columns()

    def set_empty_state(self, empty: bool, title: str = "", body: str = "") -> None:
        if title or body:
            self.empty.set_text(
                title or self.empty.title_label.text(),
                body or self.empty.body_label.text(),
            )
        self.empty.setVisible(empty)
        self.table.setVisible(not empty)

    def selected_rows(self) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        seen: set[int] = set()
        for index in self.table.selectionModel().selectedRows():
            source = self.proxy.mapToSource(index)
            if source.row() not in seen:
                row = self.model.row_at(source.row())
                if row is not None:
                    selected.append(row)
                    seen.add(source.row())
        return selected

    def _selection_changed(self) -> None:
        selected = self.selected_rows()
        if not selected:
            self.details.clear()
            return
        row = selected[0]
        raw = row.get("_raw", row)
        self.details.setPlainText(json.dumps(raw, indent=2, sort_keys=True, default=str))
        self.row_selected.emit(raw)


class CandidateTable(QWidget):
    decisions_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.decisions: dict[str, str] = {}
        self.records = RecordTable(
            [
                ("Recommendation", "kind"),
                ("Path", "path"),
                ("Confidence", "confidence"),
                ("Project", "project_root"),
                ("Decision", "decision"),
                ("Reason", "reason"),
            ],
            placeholder="Search candidates, paths, reasons, or decisions…",
            multi_select=True,
        )
        self._rows: list[dict[str, Any]] = []

        # The action row and the safety note live on separate lines. Packing
        # them into one row made this tab demand ~1100px, which forced the
        # whole workspace wider than the window at 1366x768 and pushed the
        # report actions off-screen.
        bar = QHBoxLayout()
        bar.setSpacing(6)
        # Short label: this row's five buttons already say what it does, and a
        # longer caption widened the workspace minimum enough to squeeze the
        # sidebar at 1366x768 / 125%.
        label = QLabel("Plan:")
        label.setObjectName("mutedLabel")
        label.setToolTip("Apply a planning decision to the selected candidates")
        bar.addWidget(label)
        for title, decision in (
            ("Keep", "keep"),
            ("Extract", "extract"),
            ("Archive", "archive"),
            ("Review", "review"),
        ):
            button = QPushButton(title)
            button.setProperty("kind", "decision")
            button.clicked.connect(lambda _checked=False, value=decision: self._set_decision(value))
            bar.addWidget(button)
        clear = QPushButton("Clear")
        clear.setProperty("kind", "quiet")
        clear.clicked.connect(lambda: self._set_decision(""))
        bar.addWidget(clear)
        bar.addStretch(1)

        note = QLabel("Planning only — never changes files")
        note.setObjectName("safetyLabel")
        note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(bar)
        layout.addWidget(note)
        layout.addWidget(self.records, 1)

    def load_bundle(self, bundle: DashboardBundle) -> None:
        self.decisions.clear()
        rows = []
        for kind, candidates in (
            ("extract", bundle.audit.extract_candidates),
            ("archive", bundle.audit.archive_candidates),
            ("delete-review", bundle.audit.delete_candidates),
        ):
            for candidate in candidates:
                raw = public_record(candidate)
                rows.append(
                    {
                        **raw,
                        "kind": kind,
                        "decision": "",
                        "_key": candidate_key(kind, candidate.path),
                        "_raw": raw,
                    }
                )
        self._rows = sorted(rows, key=lambda row: (row["kind"], row["path"]))
        self.records.set_rows(self._rows)

    def _set_decision(self, decision: str) -> None:
        selected = self.records.selected_rows()
        if not selected:
            return
        for row in selected:
            key = row["_key"]
            row["decision"] = decision
            if decision:
                self.decisions[key] = decision
            else:
                self.decisions.pop(key, None)
        self.records.model.layoutChanged.emit()
        self.decisions_changed.emit()


class MetricCard(_ThemedMetricCard):
    """Compact metric tile.

    A thin alias over the shared themed component so the overview and the
    console strip use one card design. Crucially the shared card has a Fixed
    vertical size policy, which is what stops these from stretching into large
    empty rectangles when the tab has spare height.
    """

    def __init__(
        self, label: str, tone: str = "neutral", parent: QWidget | None = None
    ) -> None:
        super().__init__(label, "—", tone=tone, parent=parent)
        # Back-compat alias for existing callers that reach for `.value`.
        self.value = self.value_label


class OverviewWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cards = {
            "files": MetricCard("Files observed"),
            "projects": MetricCard("Project roots"),
            "technical": MetricCard("Verified workflows", tone="evidence"),
            "candidates": MetricCard("Review candidates", tone="primary"),
            "duplicates": MetricCard("Duplicate groups", tone="evidence"),
        }
        cards = QHBoxLayout()
        cards.setSpacing(12)
        for card in self.cards.values():
            cards.addWidget(card, 1)

        self.projects = RecordTable(
            [
                ("Root", "root"),
                ("Types", "kinds"),
                ("Score", "appraisal_score"),
                ("Category", "appraisal_category"),
                ("Source", "source_files"),
                ("Tests", "test_files"),
                ("Evidence", "appraisal_reasons"),
            ],
            placeholder="Filter detected projects…",
        )
        self.pivots = QListWidget()
        self.pivots.setWordWrap(True)
        self.pivots.setAlternatingRowColors(True)
        self.pivots.setMinimumWidth(280)
        self.pivots.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Before a scan the list is empty, which previously rendered as a large
        # unexplained black void beside the project table. Swap in a compact,
        # deliberate empty state instead; no sample findings, so nothing here
        # can be mistaken for real output.
        self.pivots_empty = _EmptyState(
            "No pivot evidence yet",
            "Deterministic pivot suggestions appear here once an audit finds "
            "supported opportunities in the estate.",
            marker=_EmptyState.EVIDENCE_MARKER,
            compact=True,
        )

        content = QSplitter(Qt.Orientation.Horizontal)
        content.addWidget(self.projects)
        pivot_frame = QFrame()
        pivot_layout = QVBoxLayout(pivot_frame)
        pivot_title = QLabel("Deterministic pivot suggestions")
        pivot_title.setObjectName("sectionTitle")
        pivot_layout.addWidget(pivot_title)
        pivot_layout.addWidget(self.pivots, 1)
        # Stretch 0 plus a trailing spacer: the empty state hugs its content at
        # the top of the panel instead of expanding to fill the pane, which
        # would just replace a black void with a very tall notice.
        pivot_layout.addWidget(self.pivots_empty, 0)
        self._pivot_spacer_index = pivot_layout.count()
        pivot_layout.addStretch(0)
        self._pivot_layout = pivot_layout
        content.addWidget(pivot_frame)
        content.setStretchFactor(0, 3)
        content.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        # Cards keep their natural height; all spare space goes to the tables.
        layout.addLayout(cards, 0)
        layout.addWidget(content, 1)
        # Start in the pre-scan empty state rather than showing a bare list.
        self.set_pivots_empty(True)

    def load_bundle(self, bundle: DashboardBundle) -> None:
        audit = bundle.audit
        truth = bundle.technical_truth
        self.cards["files"].set_value(f"{len(audit.files):,}")
        self.cards["projects"].set_value(f"{len(audit.projects):,}")
        self.cards["technical"].set_value(
            str(truth.summary.get("verified_workflows", 0)) if truth else "Not run"
        )
        candidate_count = (
            len(audit.extract_candidates)
            + len(audit.archive_candidates)
            + len(audit.delete_candidates)
        )
        self.cards["candidates"].set_value(f"{candidate_count:,}")
        self.cards["duplicates"].set_value(f"{len(audit.duplicate_groups):,}")
        self.projects.set_rows(
            [{**public_record(project), "_raw": public_record(project)} for project in audit.projects]
        )
        self.pivots.clear()
        for pivot in audit.pivot_suggestions:
            self.pivots.addItem(
                f"{pivot.get('title', 'Suggestion')}\n\n"
                f"{pivot.get('idea', '')}\n\n"
                f"Evidence: {', '.join(pivot.get('evidence', []))} "
                f"• Confidence: {pivot.get('confidence', 'unknown')}"
            )
        self.set_pivots_empty(
            not audit.pivot_suggestions,
            scanned=True,
        )

    def set_pivots_empty(self, empty: bool, scanned: bool = False) -> None:
        """Show either the pivot list or its empty state, never a bare void."""

        if empty and scanned:
            self.pivots_empty.set_text(
                "No pivot evidence found",
                "This audit did not surface a deterministic pivot for the "
                "scanned estate.",
            )
        elif empty:
            self.pivots_empty.set_text(
                "No pivot evidence yet",
                "Deterministic pivot suggestions appear here once an audit "
                "finds supported opportunities in the estate.",
            )
        self.pivots_empty.setVisible(empty)
        self.pivots.setVisible(not empty)
        # Absorb the leftover height only while the compact notice is showing.
        self._pivot_layout.setStretch(self._pivot_spacer_index, 1 if empty else 0)


class TechnicalTruthWidget(QTabWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.capabilities = RecordTable(
            [
                ("Capability", "name"),
                ("Status", "status"),
                ("Confidence", "confidence_label"),
                ("Readiness", "extraction_readiness"),
                ("Coupling", "coupling"),
                ("Explanation", "explanation"),
            ],
            placeholder="Filter capabilities…",
        )
        self.workflows = RecordTable(
            [
                ("Workflow", "name"),
                ("Status", "completion_status"),
                ("Confidence", "confidence_label"),
                ("Trigger", "trigger"),
                ("Missing links", "missing_links"),
            ],
            placeholder="Filter reconstructed workflows…",
        )
        self.contradictions = RecordTable(
            [
                ("Claim", "claim"),
                ("Technical finding", "technical_finding"),
                ("Severity", "severity"),
                ("Confidence", "confidence"),
            ],
            placeholder="Filter contradictions…",
        )
        self.families = RecordTable(
            [
                ("Family", "canonical_hint"),
                ("Members", "members"),
                ("Relationship", "relationship"),
                ("Confidence", "confidence"),
                ("Recommendation", "merge_recommendation"),
            ],
            placeholder="Filter project families…",
        )
        self.addTab(self.capabilities, "Capabilities")
        self.addTab(self.workflows, "Workflows")
        self.addTab(self.contradictions, "Contradictions")
        self.addTab(self.families, "Project families")

    def load_bundle(self, bundle: DashboardBundle) -> None:
        truth = bundle.technical_truth
        if truth is None:
            for table in (
                self.capabilities,
                self.workflows,
                self.contradictions,
                self.families,
            ):
                table.set_rows([])
                table.details.setPlainText(
                    "Technical Truth was not enabled for this scan. "
                    "Choose Technical Truth or Resurrection mode and scan again."
                )
            return
        self.capabilities.set_rows(_raw_rows(truth.capabilities))
        self.workflows.set_rows(_raw_rows(truth.workflows))
        self.contradictions.set_rows(_raw_rows(truth.contradictions))
        self.families.set_rows(_raw_rows(truth.project_families))


class ArchitectureView(QGraphicsView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(self.renderHints())
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#0c1119"))

    def load_bundle(self, bundle: DashboardBundle) -> None:
        scene = self.scene()
        scene.clear()
        target = bundle.audit.target.name
        root = self._node(0, 0, target, "#e7bf73", 240)
        projects = bundle.audit.projects[:30]
        columns = max(1, min(4, len(projects)))
        project_nodes: dict[str, QGraphicsRectItem] = {}
        last_project_row = 0
        for index, project in enumerate(projects):
            row, column = divmod(index, columns)
            last_project_row = max(last_project_row, row)
            x = (column - (columns - 1) / 2) * 300
            y = 180 + row * 145
            color = (
                "#58d6a2"
                if project.appraisal_score >= 75
                else "#69a7ff"
                if project.appraisal_score >= 55
                else "#a07ee8"
                if project.appraisal_score >= 35
                else "#7e8798"
            )
            label = f"{project.root}\n{', '.join(project.kinds)} • {project.appraisal_score}/100"
            node = self._node(x, y, label, color, 245)
            node.setToolTip(
                json.dumps(public_record(project), indent=2, sort_keys=True, default=str)
            )
            project_nodes[project.root] = node
            self._edge(root, node, color)

        if not projects:
            empty = self._node(0, 180, "No project root detected", "#7e8798", 245)
            self._edge(root, empty, "#465064")

        truth = bundle.technical_truth
        if truth is not None and truth.capabilities:
            capabilities = [
                item for item in truth.capabilities if item.get("supporting_paths")
            ][:20]
            capability_columns = max(1, min(4, len(capabilities)))
            capability_y = 390 + last_project_row * 145
            for index, capability in enumerate(capabilities):
                row, column = divmod(index, capability_columns)
                x = (column - (capability_columns - 1) / 2) * 300
                y = capability_y + row * 135
                status = str(capability.get("status", "unknown")).replace("_", " ")
                label = f"{capability.get('name', 'Capability')}\n{status}"
                color = (
                    "#58d6a2"
                    if capability.get("status") == "verified_end_to_end"
                    else "#69a7ff"
                    if capability.get("status") in {
                        "partially_implemented",
                        "implemented_but_disconnected",
                    }
                    else "#a07ee8"
                )
                node = self._node(x, y, label, color, 245)
                node.setToolTip(
                    json.dumps(capability, indent=2, sort_keys=True, default=str)
                )
                source = _project_node_for_capability(
                    capability,
                    project_nodes,
                    root,
                )
                self._edge(source, node, color)
        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-80, -80, 80, 80))
        self.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def _node(
        self,
        x: float,
        y: float,
        text: str,
        color: str,
        width: float,
    ) -> QGraphicsRectItem:
        lines = text.count("\n") + 1
        height = max(64, 28 + lines * 22)
        rect = QGraphicsRectItem(-width / 2, -height / 2, width, height)
        rect.setPos(x, y)
        rect.setBrush(QColor("#151d29"))
        pen = rect.pen()
        pen.setColor(QColor(color))
        pen.setWidth(2)
        rect.setPen(pen)
        rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.scene().addItem(rect)
        label = QGraphicsTextItem(text, rect)
        label.setDefaultTextColor(QColor("#eef2f8"))
        label.setTextWidth(width - 24)
        bounds = label.boundingRect()
        label.setPos(-width / 2 + 12, -bounds.height() / 2)
        return rect

    def _edge(self, source: QGraphicsRectItem, target: QGraphicsRectItem, color: str) -> None:
        start = source.sceneBoundingRect().center()
        end = target.sceneBoundingRect().center()
        line: QGraphicsLineItem = self.scene().addLine(start.x(), start.y(), end.x(), end.y())
        pen = line.pen()
        pen.setColor(QColor(color))
        pen.setWidth(1)
        line.setPen(pen)
        line.setZValue(-1)


def _raw_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**item, "_raw": item} for item in items]


def _project_node_for_capability(
    capability: dict[str, Any],
    project_nodes: dict[str, QGraphicsRectItem],
    default: QGraphicsRectItem,
) -> QGraphicsRectItem:
    paths = [str(path) for path in capability.get("supporting_paths", [])]
    roots = sorted(project_nodes, key=lambda root: (-len(root), root))
    for root in roots:
        if root == "." or any(path == root or path.startswith(f"{root}/") for path in paths):
            return project_nodes[root]
    return default


def _display(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        if items and all(isinstance(item, dict) for item in items):
            return f"{len(items)} structured record{'s' if len(items) != 1 else ''}"
        return ", ".join(str(item) for item in items)
    if isinstance(value, dict):
        return f"{len(value)} structured field{'s' if len(value) != 1 else ''}"
    return str(value).replace("_", " ")


def _full_display(value: Any) -> str:
    if isinstance(value, (dict, list, tuple, set)):
        normalized = list(value) if isinstance(value, set) else value
        return json.dumps(normalized, indent=2, sort_keys=True, default=str)
    return _display(value)


def _sort_value(value: Any) -> tuple[int, Any]:
    if value is None:
        return (2, "")
    if isinstance(value, (int, float)):
        return (0, value)
    return (1, _display(value).casefold())
