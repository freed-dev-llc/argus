"""Discovery collector registry — name → collector class."""

from __future__ import annotations

from ..base import Collector
from .dhcp_arp import DhcpArpCollector
from .snmp_lldp import SnmpLldpCollector
from .unifi import UniFiCollector

COLLECTORS: dict[str, type[Collector]] = {
    UniFiCollector.name: UniFiCollector,
    SnmpLldpCollector.name: SnmpLldpCollector,
    DhcpArpCollector.name: DhcpArpCollector,
}

__all__ = ["COLLECTORS", "DhcpArpCollector", "SnmpLldpCollector", "UniFiCollector"]
