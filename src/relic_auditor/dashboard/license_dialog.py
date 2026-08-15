from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from .. import __version__
from ..licensing import (
    PRODUCTION_PUBLIC_KEYS,
    LicenseError,
    activate_license,
    deactivate_license,
)
from ..product_discovery.entitlements import Entitlement, FREE_ENTITLEMENT
from .components import PrimaryButton, SecondaryButton, StatusBadge
from .theme import SPACING


class _ActivationWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, license_key: str) -> None:
        super().__init__()
        self.license_key = license_key

    @Slot()
    def run(self) -> None:
        try:
            entitlement = activate_license(self.license_key, app_version=__version__)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        finally:
            self.license_key = ""
        self.finished.emit(entitlement)


class LicenseDialog(QDialog):
    entitlement_changed = Signal(object)

    def __init__(self, entitlement: Entitlement, parent=None) -> None:
        super().__init__(parent)
        self.entitlement = entitlement
        self._last_error: str | None = None
        self._thread: QThread | None = None
        self._worker: _ActivationWorker | None = None
        self.setWindowTitle("Relic plan and license")
        self.setModal(True)
        self.resize(560, 360)

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING.md)
        title = QLabel("Plan and license")
        title.setObjectName("panelTitle")
        intro = QLabel(
            "Relic verifies a signed, device-bound entitlement. A license key is sent "
            "only to the activation service and is never placed in reports or command history."
        )
        intro.setWordWrap(True)
        self.badge = StatusBadge()
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("Enter license key")
        self.key_input.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.key_input.setAccessibleName("Relic license key")
        self.activate_button = PrimaryButton("Activate on this device")
        self.activate_button.clicked.connect(self.activate)
        self.deactivate_button = SecondaryButton("Deactivate this device")
        self.deactivate_button.clicked.connect(self.deactivate)
        self.close_button = SecondaryButton("Close")
        self.close_button.clicked.connect(self.accept)

        actions = QHBoxLayout()
        actions.addWidget(self.activate_button)
        actions.addWidget(self.deactivate_button)
        actions.addStretch(1)
        actions.addWidget(self.close_button)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addWidget(self.badge)
        layout.addWidget(self.details)
        layout.addWidget(self.key_input)
        layout.addLayout(actions)
        layout.addStretch(1)
        self._refresh()

    def _refresh(self) -> None:
        tier = self.entitlement.tier.value.upper()
        licensed = self.entitlement.license_id is not None
        self.badge.set_status("ready" if licensed else "idle", f"PLAN: {tier}")
        if licensed:
            self.details.setText(
                f"Signed entitlement verified. Offline validity: "
                f"{self.entitlement.valid_until or 'not supplied'}."
            )
        elif self._last_error:
            self.details.setText(self._last_error)
        elif PRODUCTION_PUBLIC_KEYS:
            self.details.setText("No active signed license was found on this device.")
        else:
            self.details.setText(
                "The signed licensing client is installed, but production activation "
                "is not provisioned in this release candidate. Relic therefore fails closed to Free."
            )
        provisioned = bool(PRODUCTION_PUBLIC_KEYS)
        idle = self._thread is None
        self.key_input.setEnabled(provisioned and idle)
        self.activate_button.setEnabled(provisioned and idle)
        self.deactivate_button.setEnabled(licensed and idle)
        self.close_button.setEnabled(idle)

    @Slot()
    def activate(self) -> None:
        if self._thread is not None:
            return
        license_key = self.key_input.text().strip()
        self.key_input.clear()
        if not license_key:
            QMessageBox.information(self, "License activation", "Enter a license key first.")
            return
        self.badge.set_status("running", "VERIFYING SIGNED LICENSE")
        self._last_error = None
        thread = QThread(self)
        worker = _ActivationWorker(license_key)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._activated)
        worker.failed.connect(self._activation_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        self._refresh()
        thread.start()

    @Slot(object)
    def _activated(self, entitlement: Entitlement) -> None:
        self.entitlement = entitlement
        self._last_error = None
        self.entitlement_changed.emit(entitlement)
        self.badge.set_status("ready", "LICENSE VERIFIED")

    @Slot(str)
    def _activation_failed(self, message: str) -> None:
        self._last_error = message
        self.badge.set_status("failed", "ACTIVATION FAILED")
        self.details.setText(message)

    @Slot()
    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._refresh()

    @Slot()
    def deactivate(self) -> None:
        try:
            deactivate_license()
        except LicenseError as exc:
            QMessageBox.warning(self, "License deactivation", str(exc))
            return
        self.entitlement = FREE_ENTITLEMENT
        self._last_error = None
        self.entitlement_changed.emit(self.entitlement)
        self._refresh()

    def reject(self) -> None:
        if self._thread is not None:
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt naming
        if self._thread is not None:
            event.ignore()
            return
        super().closeEvent(event)
