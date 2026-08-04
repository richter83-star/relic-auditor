"""Evidence-backed, post-scan product discovery."""

from .pipeline import discover_products
from .schemas import DiscoveryConfig, DiscoveryResult

__all__ = ["DiscoveryConfig", "DiscoveryResult", "discover_products"]
