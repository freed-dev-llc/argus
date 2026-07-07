"""SNMP / LLDP discovery collector (generic, for non-UniFi gear).

Per target: SNMP GET ``sysName`` + an LLDP-MIB neighbor walk that yields links carrying
local and remote port identifiers. Configured via ``SNMP_TARGETS`` (comma-separated
``host[:community]``) and ``SNMP_COMMUNITY``, with ``SNMP_PORT``, ``SNMP_TIMEOUT``, and
``SNMP_RETRIES`` controlling the transport. Requires the optional ``discovery`` extra:
``pip install 'argus[discovery]'`` (pysnmp).

SNMPv3 is global: set ``SNMP_V3_USER`` (plus ``SNMP_V3_AUTH_KEY`` / ``SNMP_V3_AUTH_PROTOCOL``
and ``SNMP_V3_PRIV_KEY`` / ``SNMP_V3_PRIV_PROTOCOL``) to switch every target to USM. The
security level is derived from the keys: no auth key = noAuthNoPriv, auth only = authNoPriv,
auth + priv = authPriv. When v3 is on, any ``:community`` suffix in ``SNMP_TARGETS`` is
ignored and a note records the ignored value. Mixing v2c and v3 targets in one scan is
unsupported.

Targets are queried in parallel via ``asyncio.gather`` (one ``SnmpEngine`` per target, which
is fine at homelab scale). The pysnmp glue is exercised in CI by ``test_snmp_query.py``, which
replays snmpsim-style ``.snmprec`` fixtures through the real ``_query_target`` code path.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ...config import Settings, get_settings
from ..base import Collector, DiscoveredDevice, DiscoveredLink, DiscoveryResult

if TYPE_CHECKING:
    from pysnmp.hlapi.asyncio import CommunityData, UsmUserData

logger = logging.getLogger(__name__)

SYSNAME_OID = "1.3.6.1.2.1.1.5.0"

# LLDP-MIB remote-neighbor columns (lldpRemEntry 1.0.8802.1.1.2.1.4.1.1), each indexed by
# ``timeMark.localPortNum.remIndex``.
LLDP_REM_BASE = "1.0.8802.1.1.2.1.4.1.1"
LLDP_REM_CHASSIS_ID_SUBTYPE_OID = f"{LLDP_REM_BASE}.4"
LLDP_REM_CHASSIS_ID_OID = f"{LLDP_REM_BASE}.5"
LLDP_REM_PORT_ID_SUBTYPE_OID = f"{LLDP_REM_BASE}.6"
LLDP_REM_PORT_ID_OID = f"{LLDP_REM_BASE}.7"
LLDP_REM_PORT_DESC_OID = f"{LLDP_REM_BASE}.8"
LLDP_REM_SYSNAME_OID = f"{LLDP_REM_BASE}.9"

# LLDP-MIB local-port columns (lldpLocPortEntry 1.0.8802.1.1.2.1.3.7.1), indexed by localPortNum.
LLDP_LOC_PORT_BASE = "1.0.8802.1.1.2.1.3.7.1"
LLDP_LOC_PORT_ID_OID = f"{LLDP_LOC_PORT_BASE}.3"
LLDP_LOC_PORT_DESC_OID = f"{LLDP_LOC_PORT_BASE}.4"

# LldpChassisIdSubtype/LldpPortIdSubtype value 4/3 = macAddress: the OctetString holds raw
# bytes and must be rendered as colon-hex rather than decoded as text.
CHASSIS_SUBTYPE_MAC = 4
PORT_SUBTYPE_MAC = 3

# SNMPv3 protocol name -> USM constant (resolved lazily so pysnmp stays an optional import).
_AUTH_PROTOCOLS = {
    "md5": "USM_AUTH_HMAC96_MD5",
    "sha": "USM_AUTH_HMAC96_SHA",
    "sha224": "USM_AUTH_HMAC128_SHA224",
    "sha256": "USM_AUTH_HMAC192_SHA256",
    "sha384": "USM_AUTH_HMAC256_SHA384",
    "sha512": "USM_AUTH_HMAC384_SHA512",
}
_PRIV_PROTOCOLS = {
    "des": "USM_PRIV_CBC56_DES",
    "aes128": "USM_PRIV_CFB128_AES",
    "aes192": "USM_PRIV_CFB192_AES",
    "aes256": "USM_PRIV_CFB256_AES",
}


@dataclass(frozen=True)
class SnmpAuthSpec:
    """Resolved per-target auth: either a v2c community or the v3 USM fields."""

    community: str | None = None
    v3_user: str | None = None
    v3_auth_key: str | None = None
    v3_auth_protocol: str = "sha"
    v3_priv_key: str | None = None
    v3_priv_protocol: str = "aes128"

    @property
    def is_v3(self) -> bool:
        return self.v3_user is not None


@dataclass
class NeighborInfo:
    """One LLDP neighbor, joined across the remote columns and the local-port table."""

    remote_name: str
    local_port: str | None = None
    remote_port: str | None = None
    chassis_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


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


def _auth_spec_for(target_community: str, settings: Settings) -> SnmpAuthSpec:
    """Build the auth spec for one target: v3 USM when enabled, else the v2c community."""
    if settings.snmp_v3_enabled:
        return SnmpAuthSpec(
            v3_user=settings.snmp_v3_user,
            v3_auth_key=settings.snmp_v3_auth_key or None,
            v3_auth_protocol=settings.snmp_v3_auth_protocol,
            v3_priv_key=settings.snmp_v3_priv_key or None,
            v3_priv_protocol=settings.snmp_v3_priv_protocol,
        )
    return SnmpAuthSpec(community=target_community)


def _build_auth(spec: SnmpAuthSpec) -> CommunityData | UsmUserData:
    """Turn a :class:`SnmpAuthSpec` into a pysnmp auth object (import kept local)."""
    import pysnmp.hlapi.asyncio as hlapi

    if not spec.is_v3:
        return hlapi.CommunityData(spec.community, mpModel=1)

    auth_name = spec.v3_auth_protocol.lower()
    priv_name = spec.v3_priv_protocol.lower()
    if spec.v3_auth_key and auth_name not in _AUTH_PROTOCOLS:
        raise ValueError(f"Unknown SNMPv3 auth protocol '{spec.v3_auth_protocol}'.")
    if spec.v3_priv_key and priv_name not in _PRIV_PROTOCOLS:
        raise ValueError(f"Unknown SNMPv3 priv protocol '{spec.v3_priv_protocol}'.")
    auth_proto = getattr(hlapi, _AUTH_PROTOCOLS[auth_name]) if spec.v3_auth_key else None
    priv_proto = getattr(hlapi, _PRIV_PROTOCOLS[priv_name]) if spec.v3_priv_key else None
    return hlapi.UsmUserData(
        spec.v3_user,
        spec.v3_auth_key,
        spec.v3_priv_key,
        authProtocol=auth_proto,
        privProtocol=priv_proto,
    )


def _render_id(value: Any, subtype: int | None, mac_subtype: int) -> str:
    """Render an LLDP id column; a macAddress subtype becomes lowercase colon-hex.

    ``mac_subtype`` is the field-specific macAddress code (``CHASSIS_SUBTYPE_MAC`` for
    chassis ids, ``PORT_SUBTYPE_MAC`` for port ids). Keeping the check field-specific
    stops a chassis subtype 3 (portComponent) or a port subtype 4 (networkAddress) from
    being mistaken for a MAC and hex-mangled.
    """
    if subtype == mac_subtype and hasattr(value, "asOctets"):
        return ":".join(f"{b:02x}" for b in value.asOctets())
    return str(value).strip()


async def _walk_table(engine: Any, auth: Any, transport: Any, base_oid: str) -> dict[str, Any]:
    """Walk one column subtree, keyed by the OID suffix after ``base_oid`` (the row index)."""
    import pysnmp.hlapi.asyncio as hlapi

    rows: dict[str, Any] = {}
    prefix = base_oid + "."
    async for err_ind, err_stat, _, binds in hlapi.walk_cmd(
        engine,
        auth,
        transport,
        hlapi.ContextData(),
        hlapi.ObjectType(hlapi.ObjectIdentity(base_oid)),
    ):
        if err_ind or err_stat:
            break
        for oid, value in binds:
            oid_str = str(oid)
            if not oid_str.startswith(prefix):
                continue
            rows[oid_str[len(prefix):]] = value
    return rows


async def _query_target(
    host: str,
    spec: SnmpAuthSpec,
    *,
    port: int,
    timeout: float,
    retries: int,
) -> tuple[str | None, list[NeighborInfo]]:
    """Return ``(sysName, [NeighborInfo])`` for a target.

    Raises ImportError if pysnmp is absent; other failures propagate to the caller.
    """
    import pysnmp.hlapi.asyncio as hlapi

    engine = hlapi.SnmpEngine()
    auth = _build_auth(spec)
    transport = await hlapi.UdpTransportTarget.create(
        (host, port), timeout=timeout, retries=retries
    )

    err_ind, err_stat, _, var_binds = await hlapi.get_cmd(
        engine,
        auth,
        transport,
        hlapi.ContextData(),
        hlapi.ObjectType(hlapi.ObjectIdentity(SYSNAME_OID)),
    )
    if err_ind or err_stat or not var_binds:
        return None, []
    sysname = str(var_binds[0][1]).strip()

    neighbors: list[NeighborInfo] = []
    try:
        rem_sysname = await _walk_table(engine, auth, transport, LLDP_REM_SYSNAME_OID)
        rem_chassis = await _walk_table(engine, auth, transport, LLDP_REM_CHASSIS_ID_OID)
        rem_chassis_sub = await _walk_table(engine, auth, transport, LLDP_REM_CHASSIS_ID_SUBTYPE_OID)
        rem_port_id = await _walk_table(engine, auth, transport, LLDP_REM_PORT_ID_OID)
        rem_port_sub = await _walk_table(engine, auth, transport, LLDP_REM_PORT_ID_SUBTYPE_OID)
        rem_port_desc = await _walk_table(engine, auth, transport, LLDP_REM_PORT_DESC_OID)
        loc_port_id = await _walk_table(engine, auth, transport, LLDP_LOC_PORT_ID_OID)
        loc_port_desc = await _walk_table(engine, auth, transport, LLDP_LOC_PORT_DESC_OID)
    except Exception as exc:  # LLDP is optional; keep the device even if the walk fails
        logger.debug("LLDP walk failed for %s: %s", host, exc)
        return sysname, neighbors

    # Row index is ``timeMark.localPortNum.remIndex``; the local-port table is keyed by the
    # middle component (localPortNum).
    for index, name_val in rem_sysname.items():
        parts = index.split(".")
        loc_port_num = parts[1] if len(parts) >= 2 else ""

        chassis_sub = _as_int(rem_chassis_sub.get(index))
        chassis_id = None
        if index in rem_chassis:
            chassis_id = _render_id(rem_chassis[index], chassis_sub, CHASSIS_SUBTYPE_MAC)

        remote_name = str(name_val).strip()
        if not remote_name:
            remote_name = chassis_id or ""
        if not remote_name:
            continue  # both sysName and chassis id blank: nothing to key a link on

        port_sub = _as_int(rem_port_sub.get(index))
        remote_port = None
        if index in rem_port_id:
            remote_port = _render_id(rem_port_id[index], port_sub, PORT_SUBTYPE_MAC)
        if not remote_port and index in rem_port_desc:
            remote_port = _render_id(rem_port_desc[index], None, PORT_SUBTYPE_MAC)

        local_port = None
        if loc_port_num in loc_port_id:
            local_port = _render_id(loc_port_id[loc_port_num], None, PORT_SUBTYPE_MAC)
        if not local_port and loc_port_num in loc_port_desc:
            local_port = _render_id(loc_port_desc[loc_port_num], None, PORT_SUBTYPE_MAC)

        raw: dict[str, Any] = {}
        if chassis_id:
            raw["chassis_id"] = chassis_id
        if chassis_sub is not None:
            raw["chassis_id_subtype"] = chassis_sub
        neighbors.append(
            NeighborInfo(
                remote_name=remote_name,
                local_port=local_port or None,
                remote_port=remote_port or None,
                chassis_id=chassis_id,
                raw=raw,
            )
        )

    return sysname, neighbors


def _as_int(value: Any) -> int | None:
    """Coerce a pysnmp Integer (or None) to a plain int."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class SnmpLldpCollector(Collector):
    name = "snmp_lldp"

    async def collect(self) -> DiscoveryResult:
        settings = get_settings()
        result = DiscoveryResult(collector=self.name)
        targets = _parse_targets(settings.snmp_targets, settings.snmp_community)

        if not targets:
            result.notes.append("SNMP not configured: set SNMP_TARGETS (host[:community],...).")
            return result

        if settings.snmp_v3_enabled:
            ignored = sorted(
                {community for _, community in targets if community != settings.snmp_community}
            )
            if ignored:
                result.notes.append(
                    "SNMPv3 is enabled (SNMP_V3_USER set): per-target community values are "
                    f"ignored ({', '.join(ignored)})."
                )

        coros = [
            _query_target(
                host,
                _auth_spec_for(community, settings),
                port=settings.snmp_port,
                timeout=settings.snmp_timeout,
                retries=settings.snmp_retries,
            )
            for host, community in targets
        ]
        results = await asyncio.gather(*coros, return_exceptions=True)

        pysnmp_missing = False
        for (host, _community), outcome in zip(targets, results, strict=True):
            if isinstance(outcome, ImportError):
                pysnmp_missing = True
                continue
            if isinstance(outcome, BaseException):
                result.notes.append(f"SNMP query failed for {host}: {outcome}")
                continue

            sysname, neighbors = outcome
            if not sysname:
                result.notes.append(f"No SNMP response from {host}.")
                continue

            result.devices.append(DiscoveredDevice(name=sysname, primary_ip=host))
            for neighbor in neighbors:
                result.links.append(
                    DiscoveredLink(
                        local_device=sysname,
                        remote_device=neighbor.remote_name,
                        local_port=neighbor.local_port,
                        remote_port=neighbor.remote_port,
                        raw=neighbor.raw,
                    )
                )

        if pysnmp_missing:
            result.notes.append("pysnmp not installed: pip install 'argus[discovery]'.")

        result.notes.append(
            f"SNMP: {len(result.devices)} device(s), {len(result.links)} link(s) "
            f"from {len(targets)} target(s)."
        )
        return result
