from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QScrollArea,
    QVBoxLayout, QWidget,
)

from ..licensing import (
    PRICING_URL, TRUSTED_PUBLIC_KEYS, deactivate_license, import_license_file,
    installation_id,
)
from ..product_discovery.entitlements import Entitlement, FREE_ENTITLEMENT
from .components import EvidenceCard, SecondaryButton, StatusBadge
from .theme import SPACING


class LicenseDialog(QDialog):
    """Plan comparison and verified offline activation, including owner testing."""

    entitlement_changed = Signal(object)

    def __init__(
        self, entitlement: Entitlement, parent=None, *,
        store=None, public_keys=None, device_id: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.entitlement = entitlement
        self._store = store
        self._public_keys = TRUSTED_PUBLIC_KEYS if public_keys is None else public_keys
        self._device_id = device_id
        self.setWindowTitle("Your Relic plan")
        self.setAccessibleName("Your Relic plan")
        self.setModal(True)
        self.resize(640, 680)

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(SPACING.md)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        title = QLabel("YOUR PLAN")
        title.setObjectName("panelTitle")
        title.setAccessibleName("Your plan heading")
        layout.addWidget(title)

        self.badge = StatusBadge()
        layout.addWidget(self.badge)

        self.details = QLabel()
        self.details.setObjectName("mutedLabel")
        self.details.setWordWrap(True)
        layout.addWidget(self.details)

        self.free_card = EvidenceCard("FREE")
        self.free_card.set_body(
            "Scanning, core results, reusable assets, reports and history."
        )
        self.pro_card = EvidenceCard("PRO · COMING SOON")
        self.pro_card.set_body("Product Opportunities and deeper product analysis.")
        self.premium_card = EvidenceCard("PREMIUM · COMING SOON")
        self.premium_card.set_body("Build Packs and Assisted Build.")
        layout.addWidget(self.free_card)
        layout.addWidget(self.pro_card)
        layout.addWidget(self.premium_card)

        self.pricing_button = SecondaryButton("View plans && pricing")
        self.pricing_button.setAccessibleName("View Relic plans and pricing in your browser")
        self.pricing_button.clicked.connect(self.open_pricing)
        layout.addWidget(self.pricing_button)

        license_title = QLabel("HAVE A LICENSE FILE?")
        license_title.setObjectName("panelTitle")
        layout.addWidget(license_title)
        help_text = QLabel(
            "Import your signed license file to activate this installation. "
            "For owner testing, copy your installation ID to request a Premium license."
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.copy_device_button = SecondaryButton("Copy installation ID")
        self.copy_device_button.setAccessibleName("Copy installation ID for license activation")
        self.copy_device_button.clicked.connect(self.copy_device_id)
        layout.addWidget(self.copy_device_button)
        self.import_button = SecondaryButton("Import license file")
        self.import_button.setAccessibleName("Import a signed Relic license file")
        self.import_button.setEnabled(bool(self._public_keys))
        self.import_button.clicked.connect(self.choose_license_file)
        layout.addWidget(self.import_button)
        self.deactivate_button = SecondaryButton("Remove license from this device")
        self.deactivate_button.clicked.connect(self.remove_license)
        layout.addWidget(self.deactivate_button)
        self.license_message = QLabel()
        self.license_message.setWordWrap(True)
        self.license_message.setTextFormat(Qt.TextFormat.PlainText)
        self.license_message.setAccessibleName("License activation status")
        layout.addWidget(self.license_message)
        self._refresh_plan()
        layout.addStretch(1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.close_button = SecondaryButton("Close")
        self.close_button.setAccessibleName("Close plan information")
        self.close_button.clicked.connect(self.accept)
        actions.addWidget(self.close_button)
        outer.addLayout(actions)

    def _refresh_plan(self) -> None:
        active = bool(self.entitlement.license_id)
        tier = self.entitlement.tier.value.upper()
        expiry = (
            datetime.fromisoformat(self.entitlement.valid_until).astimezone(UTC)
            .strftime("%d %b %Y at %H:%M UTC")
            if self.entitlement.valid_until else "not specified"
        )
        self.badge.set_status("ready" if active else "idle", f"PLAN: {tier}")
        self.details.setText(
            f"Signed {tier.title()} access on this installation. "
            f"Valid until: {expiry}."
            if active else "Scanning, core results, reusable assets, reports and history."
        )
        self.pro_card.title_label.setText("PRO" if active else "PRO · COMING SOON")
        self.premium_card.title_label.setText("PREMIUM" if active else "PREMIUM · COMING SOON")
        self.deactivate_button.setVisible(active)

    def open_pricing(self) -> None:
        if not QDesktopServices.openUrl(QUrl(PRICING_URL)):
            self.license_message.setText(f"Open this address in your browser: {PRICING_URL}")

    def copy_device_id(self) -> None:
        try:
            value = self._device_id or installation_id()
            QApplication.clipboard().setText(value)
            self.license_message.setText("Installation ID copied. Send it to the license issuer.")
        except (RuntimeError, OSError) as exc:
            self.license_message.setText(f"Could not read the installation ID: {exc}")

    def choose_license_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Relic license", "", "Relic license (*.json *.relic-license)"
        )
        if path:
            self.apply_license_file(Path(path))

    def apply_license_file(self, path: Path) -> bool:
        try:
            entitlement = import_license_file(
                path, public_keys=self._public_keys, store=self._store,
                device_id=self._device_id,
            )
        except (RuntimeError, ValueError, OSError) as exc:
            self.license_message.setText(f"License was not imported: {exc}")
            return False
        self.entitlement = entitlement
        self._refresh_plan()
        self.license_message.setText(f"{entitlement.tier.value.title()} activated. You can continue your work.")
        self.entitlement_changed.emit(entitlement)
        return True

    def remove_license(self) -> None:
        try:
            deactivate_license(store=self._store)
        except RuntimeError as exc:
            self.license_message.setText(f"Could not remove the license: {exc}")
            return
        self.entitlement = FREE_ENTITLEMENT
        self._refresh_plan()
        self.license_message.setText("License removed. This installation is now on Free.")
        self.entitlement_changed.emit(FREE_ENTITLEMENT)
