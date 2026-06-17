"""DHCP / ARP collector (stub).

Planned P1: read DHCP leases and ARP tables to learn IP/MAC bindings.
See docs/ROADMAP.md.
"""

from __future__ import annotations

from ..base import Collector, DiscoveryResult


class DhcpArpCollector(Collector):
    name = "dhcp_arp"

    async def collect(self) -> DiscoveryResult:
        return DiscoveryResult(
            collector=self.name,
            notes=["DHCP/ARP collector not yet implemented (planned P1)."],
        )
