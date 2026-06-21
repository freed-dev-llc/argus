"""Discovery collector registry — name → collector class.

Vendor-specific collectors come from the vendor packs (``discovery/vendors``, ADR-0005);
the generic SNMP/LLDP and DHCP/ARP collectors are registered directly here. ``COLLECTORS``
is the flat name→class map the discovery/reconcile tools resolve against.
"""

from __future__ import annotations

from ..base import Collector
from ..vendors import vendor_collectors
from ..vendors.unifi import UniFiCollector  # back-compat re-export
from .dhcp_arp import DhcpArpCollector
from .snmp_lldp import SnmpLldpCollector

COLLECTORS: dict[str, type[Collector]] = {
    **vendor_collectors(),
    SnmpLldpCollector.name: SnmpLldpCollector,
    DhcpArpCollector.name: DhcpArpCollector,
}

__all__ = ["COLLECTORS", "DhcpArpCollector", "SnmpLldpCollector", "UniFiCollector"]
