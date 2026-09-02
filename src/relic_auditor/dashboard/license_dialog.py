from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout

from ..product_discovery.entitlements import Entitlement
from .components import EvidenceCard, SecondaryButton, StatusBadge
from .theme import SPACING


class LicenseDialog(QDialog):
    """Honest plan presentation while production activation is unavailable.

    The signed licensing engine remains intact and fail-closed. This surface
    deliberately exposes no key field or activation/deactivation control until
    a real production activation service and trust roots are provisioned.
    """

    entitlement_changed = Signal(object)

    def __init__(self, entitlement: Entitlement, parent=None) -> None:
        super().__init__(parent)
        self.entitlement = entitlement
        self.setWindowTitle("Your Relic plan")
        self.setAccessibleName("Your Relic plan")
        self.setModal(True)
        self.resize(600, 520)

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING.md)
        title = QLabel("YOUR PLAN")
        title.setObjectName("panelTitle")
        title.setAccessibleName("Your plan heading")
        layout.addWidget(title)

        tier = entitlement.tier.value.upper()
        self.badge = StatusBadge(
            "ready" if entitlement.license_id else "idle", f"PLAN: {tier}"
        )
        layout.addWidget(self.badge)

        self.details = QLabel(
            "Scanning, core results, reusable assets, reports and history."
            if tier == "FREE"
            else "A signed entitlement is active on this device."
        )
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
        layout.addStretch(1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.close_button = SecondaryButton("Close")
        self.close_button.setAccessibleName("Close plan information")
        self.close_button.clicked.connect(self.accept)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)
