"""pfSense/OPNsense (Netgate) vendor pack — SSH CLI and SNMP discovery."""

from __future__ import annotations

from ..pack import DEVICES, Transport, VendorPack
from .collector import CONFIG_VARS, PfSenseCollector
from .models import MANUFACTURER

PFSENSE_PACK = VendorPack(
    name=PfSenseCollector.name,
    manufacturer=MANUFACTURER,
    transport=Transport.DEVICE_SSH,  # Primary; SNMP can be used as secondary (see collector)
    capabilities=frozenset({DEVICES}),  # Supports device discovery (topology mapping not yet implemented)
    config_vars=CONFIG_VARS,
    collector=PfSenseCollector,
    practices=(),  # TODO: Add validation practices (e.g., firewall rule consistency)
    knowledge_pack="firewall",  # Mnemosyne pack that explains pfSense/OPNsense (ADR-0013)
)

__all__ = ["PFSENSE_PACK", "PfSenseCollector"]
