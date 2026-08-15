from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProductTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    PREMIUM = "premium"


class ProductCapability(str, Enum):
    AUDIT = "audit"
    OPPORTUNITIES = "opportunities"
    BUILD_PACK_PREVIEW = "build_pack_preview"
    BUILD_PACK_EXPORT = "build_pack_export"
    BUILDER_HANDOFFS = "builder_handoffs"
    PREMIUM_ROADMAP = "premium_roadmap"
    SUPERVISED_BUILD = "supervised_build"
    LICENSE_ACTIVATION = "license_activation"


_CAPABILITIES = {
    ProductTier.FREE: frozenset(
        {ProductCapability.AUDIT, ProductCapability.LICENSE_ACTIVATION}
    ),
    ProductTier.PRO: frozenset(
        {
            ProductCapability.AUDIT,
            ProductCapability.OPPORTUNITIES,
            ProductCapability.LICENSE_ACTIVATION,
        }
    ),
    ProductTier.PREMIUM: frozenset(ProductCapability),
}


@dataclass(frozen=True)
class Entitlement:
    """Verified product entitlement.

    Production loads this boundary only from a signed, device-bound token and
    defaults to Free. No CLI flag or environment variable can promote the tier.
    Tests may inject it explicitly without weakening the production path.
    """

    tier: ProductTier = ProductTier.FREE
    subject: str = "local-default"
    source: str = "production-default"
    license_id: str | None = None
    valid_until: str | None = None

    def allows(self, capability: ProductCapability) -> bool:
        return capability in _CAPABILITIES[self.tier]

    def require(self, capability: ProductCapability) -> None:
        if not self.allows(capability):
            raise PermissionError(
                f"{capability.value} requires a higher Relic entitlement"
            )

    def public(self) -> dict[str, object]:
        return {
            "tier": self.tier.value,
            "capabilities": sorted(item.value for item in _CAPABILITIES[self.tier]),
            "source": self.source,
            "licensed": self.license_id is not None,
            "valid_until": self.valid_until,
        }


FREE_ENTITLEMENT = Entitlement()


def entitlement_for_testing(tier: ProductTier | str) -> Entitlement:
    """Explicit injection point used by verified hosts and tests only."""

    return Entitlement(ProductTier(tier), "test-host", "injected-test-boundary")
