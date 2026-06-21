"""UniFi (Ubiquiti) vendor pack — the reference, in-tree, public pack (ADR-0005)."""

from __future__ import annotations

from ..pack import CLIENTS, DEVICES, TOPOLOGY, Transport, VendorPack
from .collector import UniFiCollector
from .models import MANUFACTURER

UNIFI_PACK = VendorPack(
    name=UniFiCollector.name,
    manufacturer=MANUFACTURER,
    transport=Transport.CONTROLLER_API,
    capabilities=frozenset({DEVICES, CLIENTS, TOPOLOGY}),
    config_vars=("UNIFI_URL", "UNIFI_API_TOKEN", "UNIFI_SITE", "UNIFI_VERIFY_SSL"),
    collector=UniFiCollector,
)

__all__ = ["UNIFI_PACK", "UniFiCollector"]
