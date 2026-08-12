"""Evidence-backed, post-scan product discovery."""

from .pipeline import discover_products
from .schemas import DiscoveryConfig, DiscoveryResult
from .compatibility import (
    CompatibleOpportunities,
    load_opportunities,
    normalize_opportunity,
)
from .entitlements import (
    Entitlement,
    FREE_ENTITLEMENT,
    ProductCapability,
    ProductTier,
)

__all__ = [
    "CompatibleOpportunities",
    "DiscoveryConfig",
    "DiscoveryResult",
    "Entitlement",
    "FREE_ENTITLEMENT",
    "ProductCapability",
    "ProductTier",
    "discover_products",
    "load_opportunities",
    "normalize_opportunity",
]
