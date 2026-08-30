"""NetBird mesh discovery pack (ADR-0017)."""

from __future__ import annotations

from ..pack import DEVICES, Transport, VendorPack
from .collector import NetBirdCollector

NETBIRD_PACK = VendorPack(
    name=NetBirdCollector.name,
    manufacturer="NetBird",
    transport=Transport.MESH_API,
    capabilities=frozenset({DEVICES}),
    config_vars=(
        "NETBIRD_URL",
        "NETBIRD_API_TOKEN",
        "NETBIRD_GROUP",
        "NETBIRD_VERIFY_SSL",
        "NETBIRD_TIMEOUT",
        "NETBIRD_SITE",
        "NETBIRD_ROLE",
        "NETBIRD_MODEL",
        "NETBIRD_MANUFACTURER",
    ),
    collector=NetBirdCollector,
)

__all__ = ["NETBIRD_PACK", "NetBirdCollector"]
