from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..build_packs import BuildPackService, PreparedBuildPack
from ..product_discovery.entitlements import ProductCapability
from .components import PrimaryButton, SecondaryButton


class BuildPackDialog(QDialog):
    """Contained, accessible review wizard; it never runs a coding agent."""

    STEP_TITLES = (
        "Review product",
        "Review MVP scope",
        "Approve exact assets",
        "Review plan and criteria",
        "Choose builder handoff",
    )

    def __init__(
        self,
        service: BuildPackService,
        pack: PreparedBuildPack,
        output_root: Path,
        parent=None,
    ) -> None:
        service.entitlement.require(ProductCapability.BUILD_PACK_PREVIEW)
        super().__init__(parent)
        self.service = service
        self.pack = pack
        self.output_root = output_root
        self.setWindowTitle("Prepare this product")
        self.setAccessibleName("Prepare this product Build Pack wizard")
        self.setModal(True)

        layout = QVBoxLayout(self)
        self.step_label = QLabel()
        self.step_label.setAccessibleName("Build Pack wizard step")
        layout.addWidget(self.step_label)
        self.stack = QStackedWidget()
        self.stack.setAccessibleName("Build Pack review steps")
        layout.addWidget(self.stack, 1)

        opportunity = pack.content["opportunity"]
        self.stack.addWidget(
            self._text_page(
                "Product", f"{opportunity['title']}\n\n{opportunity['summary']}"
            )
        )
        self.stack.addWidget(self._text_page("MVP scope", str(pack.content["scope"])))
        self.asset_page = QWidget()
        asset_layout = QVBoxLayout(self.asset_page)
        asset_label = QLabel(
            "Select only assets you have reviewed and approve for copying."
        )
        asset_label.setWordWrap(True)
        asset_layout.addWidget(asset_label)
        self.asset_list = QListWidget()
        self.asset_list.setAccessibleName("Exact reusable assets requiring approval")
        for asset in pack.content["assets"]:
            item = QListWidgetItem(
                f"{asset['source_path']} — {asset['classification']}"
            )
            item.setData(Qt.ItemDataRole.UserRole, asset["source_path"])
            flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            if asset["classification"] == "blocked":
                flags &= ~Qt.ItemFlag.ItemIsEnabled
            item.setFlags(flags)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.asset_list.addItem(item)
        asset_layout.addWidget(self.asset_list)
        self.review_ack = QCheckBox("I reviewed every selected review-required asset")
        self.review_ack.setAccessibleName(
            "Acknowledge review-required asset provenance and license review"
        )
        asset_layout.addWidget(self.review_ack)
        self.stack.addWidget(self.asset_page)
        self.stack.addWidget(
            self._text_page("Plan and criteria", str(pack.content["tasks"]))
        )
        self.stack.addWidget(
            self._text_page(
                "Builder handoff",
                "Codex, Claude Code, and generic render-only handoffs will be included.",
            )
        )

        actions = QHBoxLayout()
        self.cancel_button = SecondaryButton("Cancel")
        self.cancel_button.setAccessibleName("Cancel Build Pack preparation")
        self.cancel_button.clicked.connect(self.reject)
        self.back_button = SecondaryButton("Back")
        self.back_button.setAccessibleName("Previous Build Pack step")
        self.back_button.clicked.connect(self.previous_step)
        self.next_button = PrimaryButton("Next")
        self.next_button.setAccessibleName("Next Build Pack step")
        self.next_button.clicked.connect(self.next_step)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        actions.addWidget(self.back_button)
        actions.addWidget(self.next_button)
        layout.addLayout(actions)
        QWidget.setTabOrder(self.cancel_button, self.back_button)
        QWidget.setTabOrder(self.back_button, self.next_button)
        self._sync()

    def _text_page(self, title: str, body: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        heading = QLabel(title)
        heading.setAccessibleName(f"{title} heading")
        body_label = QLabel(body)
        body_label.setWordWrap(True)
        body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(heading)
        layout.addWidget(body_label)
        layout.addStretch(1)
        return page

    def _sync(self) -> None:
        index = self.stack.currentIndex()
        self.step_label.setText(
            f"Step {index + 1} of {self.stack.count()} · {self.STEP_TITLES[index]}"
        )
        self.back_button.setEnabled(index > 0)
        self.next_button.setText(
            "Finish review" if index == self.stack.count() - 1 else "Next"
        )

    def next_step(self) -> None:
        if self.stack.currentIndex() < self.stack.count() - 1:
            self.stack.setCurrentIndex(self.stack.currentIndex() + 1)
            self._sync()
        else:
            self.accept()

    def previous_step(self) -> None:
        if self.stack.currentIndex() > 0:
            self.stack.setCurrentIndex(self.stack.currentIndex() - 1)
            self._sync()

    def selected_assets(self) -> tuple[str, ...]:
        return tuple(
            str(item.data(Qt.ItemDataRole.UserRole))
            for index in range(self.asset_list.count())
            if (item := self.asset_list.item(index)).checkState()
            == Qt.CheckState.Checked
        )

    def approval_manifest(self):
        selected = self.selected_assets()
        reviewed = selected if self.review_ack.isChecked() else ()
        return self.service.approve(self.pack, selected, reviewed_paths=reviewed)

    def export_selected(self):
        return self.service.export(
            self.pack, self.approval_manifest(), self.output_root
        )
