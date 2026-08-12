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


_CAPABILITIES = {
    ProductTier.FREE: frozenset({ProductCapability.AUDIT}),
    ProductTier.PRO: frozenset(
        {ProductCapability.AUDIT, ProductCapability.OPPORTUNITIES}
    ),
    ProductTier.PREMIUM: frozenset(ProductCapability),
}


@dataclass(frozen=True)
class Entitlement:
    """Host-injected product entitlement.

    This is an engine boundary, not a licensing server. Production defaults to
    Free and no CLI flag or environment variable can promote the tier.
    """

    tier: ProductTier = ProductTier.FREE
    subject: str = "local-default"
    source: str = "production-default"

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
        }


FREE_ENTITLEMENT = Entitlement()


def entitlement_for_testing(tier: ProductTier | str) -> Entitlement:
    """Explicit injection point used by verified hosts and tests only."""

    return Entitlement(ProductTier(tier), "test-host", "injected-test-boundary")
