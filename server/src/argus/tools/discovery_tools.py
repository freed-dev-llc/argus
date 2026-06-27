"""Discovery tools — observe live network state via pluggable collectors."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..discovery.collectors import COLLECTORS
from ..discovery.vendors import VENDOR_PACKS


def _collector_entry(name: str) -> dict[str, Any]:
    """Describe one collector: bare name, plus vendor-pack metadata when pack-backed."""
    pack = VENDOR_PACKS.get(name)
    if pack is None:
        return {"name": name, "vendor_pack": False}
    return {
        "name": name,
        "vendor_pack": True,
        "manufacturer": pack.manufacturer,
        "transport": pack.transport.value,
        "capabilities": sorted(pack.capabilities),
        "config_vars": list(pack.config_vars),
    }


async def list_collectors() -> dict[str, Any]:
    """List the available discovery collectors with vendor-pack metadata."""
    return {"collectors": [_collector_entry(name) for name in sorted(COLLECTORS)]}


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
        "links": [asdict(link) for link in result.links],
        "ip_addresses": result.ip_addresses,
        "notes": result.notes,
    }


async def network_topology(collector: str = "unifi") -> dict[str, Any]:
    """Return the observed network topology — device nodes + links — from a collector.

    Args:
        collector: Collector name (default "unifi").
    """
    cls = COLLECTORS.get(collector)
    if cls is None:
        return {"error": f"Unknown collector '{collector}'. Available: {sorted(COLLECTORS)}"}
    result = await cls().collect()
    nodes = [
        {"name": d.name, "role": d.role, "site": d.site, "primary_ip": d.primary_ip}
        for d in result.devices
    ]
    links = [
        {"source": link.local_device, "target": link.remote_device} for link in result.links
    ]
    return {"collector": result.collector, "nodes": nodes, "links": links, "notes": result.notes}
