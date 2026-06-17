"""SNMP / LLDP collector (stub).

Planned P1: walk SNMP and LLDP neighbor tables to learn devices and topology.
See docs/ROADMAP.md.
"""

from __future__ import annotations

from ..base import Collector, DiscoveryResult


class SnmpLldpCollector(Collector):
    name = "snmp_lldp"

    async def collect(self) -> DiscoveryResult:
        return DiscoveryResult(
            collector=self.name,
            notes=["SNMP/LLDP collector not yet implemented (planned P1)."],
        )
