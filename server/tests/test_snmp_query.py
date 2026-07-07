"""Tests that run the real pysnmp glue in :mod:`argus.discovery.collectors.snmp_lldp`.

pysnmp is a dev dependency (see ``pyproject.toml``), so these tests build real ``Integer`` /
``OctetString`` values and drive ``_query_target`` through fakes for ``get_cmd`` / ``walk_cmd`` /
``UdpTransportTarget`` that replay snmpsim-style ``.snmprec`` fixtures without opening a socket.
``_query_target`` re-imports ``pysnmp.hlapi.asyncio`` on every call, so patching the module's
attributes takes effect.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from argus.discovery.collectors import snmp_lldp
from argus.discovery.collectors.snmp_lldp import (
    SnmpAuthSpec,
    _build_auth,
    _query_target,
    _render_id,
)

FIXTURES = Path(__file__).parent / "fixtures" / "snmp"


def _load_snmprec(name: str) -> dict[str, object]:
    """Parse a ``.snmprec`` fixture into ``{oid: pysnmp value}`` using real value types."""
    from pysnmp.hlapi.asyncio import Integer, OctetString

    oid_map: dict[str, object] = {}
    for raw in (FIXTURES / name).read_text().splitlines():
        if not raw.strip():
            continue
        oid, tag, value = raw.split("|", 2)
        if tag == "2":
            oid_map[oid] = Integer(int(value))
        elif tag == "4x":
            oid_map[oid] = OctetString(hexValue=value)
        elif tag == "4":
            oid_map[oid] = OctetString(value)
        else:  # pragma: no cover - fixtures only use the tags above
            raise ValueError(f"Unsupported snmprec tag {tag!r} for {oid}")
    return oid_map


def _oid_of(object_type) -> str:
    """Extract the numeric OID string from an unresolved pysnmp ObjectType."""
    identity = object_type._ObjectType__args[0]
    return str(identity._ObjectIdentity__args[0])


class _FakeTransport:
    """Records the transport args instead of opening a UDP socket."""

    last_call: dict[str, object] = {}

    @classmethod
    async def create(cls, address, *args, **kwargs):
        cls.last_call = {"address": address, "args": args, "kwargs": kwargs}
        return cls()


def _patch_pysnmp(
    monkeypatch,
    oid_map: dict[str, object],
    *,
    err_ind: object | None = None,
    err_stat: int = 0,
) -> type[_FakeTransport]:
    """Patch ``get_cmd`` / ``walk_cmd`` / ``UdpTransportTarget`` to replay ``oid_map``."""
    import pysnmp.hlapi.asyncio as hlapi

    async def fake_get_cmd(engine, auth, transport, context, *var_binds):
        oid = _oid_of(var_binds[0])
        if err_ind or err_stat:
            return err_ind, err_stat, 0, []
        if oid in oid_map:
            return None, 0, 0, [(oid, oid_map[oid])]
        return None, 0, 0, []

    async def fake_walk_cmd(engine, auth, transport, context, var_bind):
        base = _oid_of(var_bind)
        prefix = base + "."
        for oid in sorted(oid_map):
            if oid == base or oid.startswith(prefix):
                yield None, 0, 0, [(oid, oid_map[oid])]

    transport = _FakeTransport
    transport.last_call = {}
    monkeypatch.setattr(hlapi, "get_cmd", fake_get_cmd)
    monkeypatch.setattr(hlapi, "walk_cmd", fake_walk_cmd)
    monkeypatch.setattr(hlapi, "UdpTransportTarget", transport)
    return transport


async def test_query_target_v2c_happy_path(monkeypatch):
    _patch_pysnmp(monkeypatch, _load_snmprec("public.snmprec"))
    sysname, neighbors = await _query_target(
        "10.0.0.1", SnmpAuthSpec(community="public"), port=161, timeout=1.0, retries=5
    )
    assert sysname == "core-sw"
    assert len(neighbors) == 2

    by_name = {n.remote_name: n for n in neighbors}
    # Neighbor A: named via lldpRemSysName, interfaceName port id, local port from lldpLocPortId.
    agg = by_name["agg-sw"]
    assert agg.local_port == "Gi0/1"
    assert agg.remote_port == "Gi1/0/24"


async def test_query_target_blank_sysname_falls_back_to_chassis_mac(monkeypatch):
    _patch_pysnmp(monkeypatch, _load_snmprec("public.snmprec"))
    _, neighbors = await _query_target(
        "10.0.0.1", SnmpAuthSpec(community="public"), port=161, timeout=1.0, retries=5
    )
    # The second neighbor has a blank lldpRemSysName; its name is the colon-hex chassis MAC.
    fallback = next(n for n in neighbors if n.remote_name == "00:1b:21:40:de:bb")
    assert fallback.local_port == "Gi0/2"
    # Port id subtype 3 (macAddress) is rendered as colon-hex too.
    assert fallback.remote_port == "00:1b:21:40:de:cc"
    assert fallback.raw["chassis_id"] == "00:1b:21:40:de:bb"


async def test_query_target_error_indication_returns_none(monkeypatch):
    _patch_pysnmp(
        monkeypatch, _load_snmprec("public.snmprec"), err_ind="requestTimedOut"
    )
    sysname, neighbors = await _query_target(
        "10.0.0.1", SnmpAuthSpec(community="public"), port=161, timeout=1.0, retries=5
    )
    assert sysname is None
    assert neighbors == []


async def test_query_target_error_status_returns_none(monkeypatch):
    _patch_pysnmp(monkeypatch, _load_snmprec("public.snmprec"), err_stat=5)
    sysname, neighbors = await _query_target(
        "10.0.0.1", SnmpAuthSpec(community="public"), port=161, timeout=1.0, retries=5
    )
    assert sysname is None
    assert neighbors == []


async def test_query_target_empty_lldp_walk_keeps_device(monkeypatch):
    _patch_pysnmp(monkeypatch, _load_snmprec("nolldp.snmprec"))
    sysname, neighbors = await _query_target(
        "10.0.0.1", SnmpAuthSpec(community="public"), port=161, timeout=1.0, retries=5
    )
    assert sysname == "lonely-host"
    assert neighbors == []


async def test_query_target_forwards_port_timeout_retries(monkeypatch):
    transport = _patch_pysnmp(monkeypatch, _load_snmprec("public.snmprec"))
    await _query_target(
        "10.0.0.9", SnmpAuthSpec(community="public"), port=1611, timeout=2.5, retries=2
    )
    assert transport.last_call["address"] == ("10.0.0.9", 1611)
    assert transport.last_call["kwargs"] == {"timeout": 2.5, "retries": 2}


def test_build_auth_community_uses_mpmodel_1():
    from pysnmp.hlapi.asyncio import CommunityData

    auth = _build_auth(SnmpAuthSpec(community="public"))
    assert isinstance(auth, CommunityData)
    assert auth.message_processing_model == 1


def test_build_auth_v3_authpriv():
    from pysnmp.hlapi.asyncio import (
        USM_AUTH_HMAC192_SHA256,
        USM_PRIV_CFB128_AES,
        UsmUserData,
    )

    auth = _build_auth(
        SnmpAuthSpec(
            v3_user="argus",
            v3_auth_key="authpass123",
            v3_auth_protocol="sha256",
            v3_priv_key="privpass123",
            v3_priv_protocol="aes128",
        )
    )
    assert isinstance(auth, UsmUserData)
    assert auth.authentication_protocol == USM_AUTH_HMAC192_SHA256
    assert auth.privacy_protocol == USM_PRIV_CFB128_AES


def test_build_auth_v3_authnopriv():
    from pysnmp.hlapi.asyncio import usmNoPrivProtocol

    auth = _build_auth(
        SnmpAuthSpec(v3_user="argus", v3_auth_key="authpass123", v3_auth_protocol="sha")
    )
    assert auth.privacy_protocol == usmNoPrivProtocol


def test_build_auth_v3_noauthnopriv():
    from pysnmp.hlapi.asyncio import usmNoAuthProtocol, usmNoPrivProtocol

    auth = _build_auth(SnmpAuthSpec(v3_user="argus"))
    assert auth.authentication_protocol == usmNoAuthProtocol
    assert auth.privacy_protocol == usmNoPrivProtocol


def test_build_auth_rejects_unknown_auth_protocol():
    with pytest.raises(ValueError, match="auth protocol"):
        _build_auth(
            SnmpAuthSpec(v3_user="argus", v3_auth_key="k", v3_auth_protocol="bogus")
        )


def test_build_auth_rejects_unknown_priv_protocol():
    with pytest.raises(ValueError, match="priv protocol"):
        _build_auth(
            SnmpAuthSpec(
                v3_user="argus",
                v3_auth_key="k",
                v3_auth_protocol="sha",
                v3_priv_key="k",
                v3_priv_protocol="bogus",
            )
        )


def test_render_id_chassis_mac_subtype_is_colon_hex():
    from pysnmp.hlapi.asyncio import OctetString

    value = OctetString(hexValue="001b2140deac")
    assert (
        _render_id(value, snmp_lldp.CHASSIS_SUBTYPE_MAC, snmp_lldp.CHASSIS_SUBTYPE_MAC)
        == "00:1b:21:40:de:ac"
    )


def test_render_id_port_mac_subtype_is_colon_hex():
    from pysnmp.hlapi.asyncio import OctetString

    value = OctetString(hexValue="001b2140decc")
    assert (
        _render_id(value, snmp_lldp.PORT_SUBTYPE_MAC, snmp_lldp.PORT_SUBTYPE_MAC)
        == "00:1b:21:40:de:cc"
    )


def test_render_id_chassis_subtype_3_stays_text():
    # Chassis-id subtype 3 is portComponent (text); only chassis subtype 4 is a MAC.
    from pysnmp.hlapi.asyncio import OctetString

    assert _render_id(OctetString("eth0"), 3, snmp_lldp.CHASSIS_SUBTYPE_MAC) == "eth0"


def test_render_id_port_subtype_4_stays_text():
    # Port-id subtype 4 is networkAddress (text); only port subtype 3 is a MAC.
    from pysnmp.hlapi.asyncio import OctetString

    assert _render_id(OctetString("192.0.2.1"), 4, snmp_lldp.PORT_SUBTYPE_MAC) == "192.0.2.1"


def test_render_id_text_subtype_is_stripped_string():
    from pysnmp.hlapi.asyncio import OctetString

    assert _render_id(OctetString(" Gi0/1 "), 5, snmp_lldp.CHASSIS_SUBTYPE_MAC) == "Gi0/1"
