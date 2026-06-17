"""SNMP / LLDP discovery collector (generic, for non-UniFi gear).

Per target: SNMP GET ``sysName`` + an LLDP-MIB neighbor walk for links. Configured via
``SNMP_TARGETS`` (comma-separated ``host[:community]``) and ``SNMP_COMMUNITY``. Requires the
optional ``discovery`` extra: ``pip install 'argus[discovery]'`` (pysnmp).

NOTE: the pysnmp glue (`_query_target`) is best-effort and **unvalidated against live SNMP
devices**; the collector logic (config parsing, mapping, links) is unit-tested by mocking it.
"""

from __future__ import annotations

import logging

from ...config import get_settings
from ..base import Collector, DiscoveredDevice, DiscoveredLink, DiscoveryResult

logger = logging.getLogger(__name__)

SYSNAME_OID = "1.3.6.1.2.1.1.5.0"
LLDP_REM_SYSNAME_OID = "1.0.8802.1.1.2.1.4.1.1.9"


def _parse_targets(raw: str, default_community: str) -> list[tuple[str, str]]:
    """Parse ``host[:community],host2,...`` into (host, community) pairs."""
    targets: list[tuple[str, str]] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        host, _, community = item.partition(":")
        targets.append((host.strip(), community.strip() or default_community))
    return targets


async def _query_target(host: str, community: str) -> tuple[str | None, list[str]]:
    """Return ``(sysName, [neighbor sysNames])`` for a target. Raises ImportError if pysnmp
    is absent; other failures are caught by the caller."""
    from pysnmp.hlapi.asyncio import (
        CommunityData,
        ContextData,
        ObjectIdentity,
        ObjectType,
        SnmpEngine,
        UdpTransportTarget,
        get_cmd,
        walk_cmd,
    )

    engine = SnmpEngine()
    auth = CommunityData(community, mpModel=1)
    transport = await UdpTransportTarget.create((host, 161))

    err_ind, err_stat, _, var_binds = await get_cmd(
        engine, auth, transport, ContextData(), ObjectType(ObjectIdentity(SYSNAME_OID))
    )
    if err_ind or err_stat or not var_binds:
        return None, []
    sysname = str(var_binds[0][1])

    neighbors: list[str] = []
    try:
        async for w_err_ind, w_err_stat, _, w_binds in walk_cmd(
            engine, auth, transport, ContextData(), ObjectType(ObjectIdentity(LLDP_REM_SYSNAME_OID))
        ):
            if w_err_ind or w_err_stat:
                break
            for _, value in w_binds:
                name = str(value).strip()
                if name:
                    neighbors.append(name)
    except Exception as exc:  # LLDP is optional; keep the device even if the walk fails
        logger.debug("LLDP walk failed for %s: %s", host, exc)

    return sysname, neighbors


class SnmpLldpCollector(Collector):
    name = "snmp_lldp"

    async def collect(self) -> DiscoveryResult:
        settings = get_settings()
        result = DiscoveryResult(collector=self.name)
        targets = _parse_targets(settings.snmp_targets, settings.snmp_community)

        if not targets:
            result.notes.append("SNMP not configured: set SNMP_TARGETS (host[:community],...).")
            return result

        for host, community in targets:
            try:
                sysname, neighbors = await _query_target(host, community)
            except ImportError:
                result.notes.append("pysnmp not installed: pip install 'argus[discovery]'.")
                return result
            except Exception as exc:
                result.notes.append(f"SNMP query failed for {host}: {exc}")
                continue

            if not sysname:
                result.notes.append(f"No SNMP response from {host}.")
                continue

            result.devices.append(DiscoveredDevice(name=sysname, primary_ip=host))
            for neighbor in neighbors:
                result.links.append(DiscoveredLink(local_device=sysname, remote_device=neighbor))

        result.notes.append(
            f"SNMP: {len(result.devices)} device(s), {len(result.links)} link(s) "
            f"from {len(targets)} target(s)."
        )
        return result
