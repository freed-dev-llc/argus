"""UniFi collector (stub).

Planned P1: pull sites/devices/clients from a UniFi controller (reuse the approach in
the sibling ``aria-unifi-mcp`` server). See docs/ROADMAP.md.
"""

from __future__ import annotations

from ..base import Collector, DiscoveryResult


class UniFiCollector(Collector):
    name = "unifi"

    async def collect(self) -> DiscoveryResult:
        return DiscoveryResult(
            collector=self.name,
            notes=["UniFi collector not yet implemented (planned P1)."],
        )
