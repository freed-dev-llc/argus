"""Discovery tools — observe live network state via pluggable collectors."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..discovery.collectors import COLLECTORS


async def list_collectors() -> dict[str, Any]:
    """List the available discovery collector names."""
    return {"collectors": sorted(COLLECTORS)}


async def discovery_scan(collector: str) -> dict[str, Any]:
    """Run a discovery collector to observe current network state.

    Args:
        collector: Collector name from ``list_collectors`` (e.g. "unifi", "snmp_lldp",
            "dhcp_arp").
    """
    cls = COLLECTORS.get(collector)
    if cls is None:
        return {"error": f"Unknown collector '{collector}'. Available: {sorted(COLLECTORS)}"}
    result = await cls().collect()
    return {
        "collector": result.collector,
        "devices": [asdict(d) for d in result.devices],
        "clients": [asdict(c) for c in result.clients],
        "ip_addresses": result.ip_addresses,
        "notes": result.notes,
    }
