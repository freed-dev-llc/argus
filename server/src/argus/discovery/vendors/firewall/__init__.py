"""Firewall vendor pack — pfSense (Netgate) and OPNsense (Deciso) SSH/SNMP discovery."""

from __future__ import annotations

from ..pack import DEVICES, Transport, VendorPack
from .collector import CONFIG_VARS, FirewallCollector
from .models import MANUFACTURER

FIREWALL_PACK = VendorPack(
    name=FirewallCollector.name,
    # Default pack-level manufacturer; per-device it is refined to Netgate (pfSense) or
    # Deciso (OPNsense) from the discovered version string (see models.manufacturer_from_version).
    manufacturer=MANUFACTURER,
    transport=Transport.DEVICE_SSH,  # Primary; SNMP can be used as secondary (see collector)
    capabilities=frozenset({DEVICES}),  # Supports device discovery (topology mapping not yet implemented)
    config_vars=CONFIG_VARS,
    collector=FirewallCollector,
    practices=(),  # TODO: Add validation practices (e.g., firewall rule consistency)
    knowledge_pack="firewall",  # Mnemosyne pack that explains pfSense/OPNsense (ADR-0013)
    # Legacy name kept resolvable so `collector=pfsense` and older tooling keep working.
    aliases=("pfsense",),
)

__all__ = ["FIREWALL_PACK", "FirewallCollector"]
