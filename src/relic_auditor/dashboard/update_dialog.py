"""Step-by-step Windows update dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
)

from ..updater import UpdateManifest
from .components import PrimaryButton, RelicPanel, SecondaryButton, StatusBadge
from .theme import BREAKPOINTS, SPACING


class UpdateDialog(QDialog):
    """Expose version, verification, and installation as three explicit steps."""

    download_requested = Signal()
    install_requested = Signal()

    def __init__(
        self,
        current_version: str,
        manifest: UpdateManifest,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.manifest = manifest
        self._mode = "download"
        self.setWindowTitle("Update Relic Auditor")
        self.setModal(True)
        self.setMinimumWidth(min(620, BREAKPOINTS.minimum_width))

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        root.setSpacing(SPACING.lg)

        panel = RelicPanel(
            "Relic Auditor update",
            "The current installation will be replaced in place; reports and settings stay where they are.",
            emphasis=True,
        )
        self.step_badge = StatusBadge("primary", "STEP 1 OF 3")
        panel.add_header_widget(self.step_badge)

        versions = QLabel(
            f"Installed: v{current_version}     Available: v{manifest.version}"
        )
        versions.setObjectName("panelTitle")
        versions.setWordWrap(True)
        panel.add_widget(versions)

        notes_text = "\n".join(f"• {note}" for note in manifest.release_notes)
        self.notes = QLabel(notes_text or "Maintenance and reliability improvements.")
        self.notes.setObjectName("mutedLabel")
        self.notes.setWordWrap(True)
        panel.add_widget(self.notes)

        self.status = QLabel(
            "Next, Relic downloads the installer and verifies its exact SHA-256 "
            "and Dracanus AI Windows publisher signature."
        )
        self.status.setObjectName("mutedLabel")
        self.status.setWordWrap(True)
        panel.add_widget(self.status)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        self.progress.setAccessibleName("Update download progress")
        panel.add_widget(self.progress)
        root.addWidget(panel)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.later_button = SecondaryButton("Later")
        self.later_button.clicked.connect(self.reject)
        actions.addWidget(self.later_button)
        self.action_button = PrimaryButton("Download and verify")
        self.action_button.clicked.connect(self._perform_action)
        actions.addWidget(self.action_button)
        root.addLayout(actions)

    def _perform_action(self) -> None:
        if self._mode == "download":
            self.download_requested.emit()
        elif self._mode == "install":
            self.install_requested.emit()

    def reject(self) -> None:
        if self._mode == "busy":
            return
        super().reject()

    def set_downloading(self) -> None:
        self._mode = "busy"
        self.step_badge.set_status("active", "STEP 2 OF 3")
        self.status.setText(
            "Downloading the installer. It cannot run until both integrity and "
            "publisher verification succeed."
        )
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.action_button.setText("Downloading…")
        self.action_button.setEnabled(False)
        self.later_button.setEnabled(False)

    def set_download_progress(self, received: int, total: int) -> None:
        if total <= 0:
            self.progress.setRange(0, 0)
            return
        self.progress.setRange(0, 100)
        self.progress.setValue(min(100, int(received * 100 / total)))

    def set_ready(self, installer_path: Path) -> None:
        self._mode = "install"
        self.step_badge.set_status("success", "STEP 3 OF 3")
        self.status.setText(
            "Verified. Choose Install update to close Relic and start the normal "
            f"Windows upgrade.\n\nReady: {installer_path.name}"
        )
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.action_button.setText("Install update")
        self.action_button.setEnabled(True)
        self.later_button.setEnabled(True)

    def set_error(self, message: str) -> None:
        self._mode = "download"
        self.step_badge.set_status("failed", "UPDATE BLOCKED")
        self.status.setText(message)
        self.progress.setVisible(False)
        self.action_button.setText("Try again")
        self.action_button.setEnabled(True)
        self.later_button.setEnabled(True)
