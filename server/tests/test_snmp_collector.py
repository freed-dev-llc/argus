"""Tests for the SNMP/LLDP collector (offline — the pysnmp query is mocked).

These cover the collector's orchestration: target parsing, parallel queries, note emission,
and link mapping. The real pysnmp glue is exercised separately in ``test_snmp_query.py``.
"""

from __future__ import annotations

import asyncio

from argus.config import Settings
from argus.discovery.collectors import snmp_lldp
from argus.discovery.collectors.snmp_lldp import (
    NeighborInfo,
    SnmpAuthSpec,
    SnmpLldpCollector,
    _parse_targets,
)


def test_parse_targets():
    assert _parse_targets("10.0.0.1, 10.0.0.2:secret ,", "public") == [
        ("10.0.0.1", "public"),
        ("10.0.0.2", "secret"),
    ]


def _settings(targets: str, **kwargs) -> Settings:
    return Settings(
        snmp_targets=targets, snmp_community="public", _env_file=None, **kwargs
    )


async def test_collect_unconfigured(monkeypatch):
    monkeypatch.setattr(snmp_lldp, "get_settings", lambda: _settings(""))
    out = await SnmpLldpCollector().collect()
    assert out.devices == []
    assert any("not configured" in note for note in out.notes)


async def test_collect_maps_devices_and_links(monkeypatch):
    monkeypatch.setattr(snmp_lldp, "get_settings", lambda: _settings("10.0.0.1"))

    async def fake_query(host, spec, *, port, timeout, retries):
        return "core-sw", [
            NeighborInfo(remote_name="agg-sw", local_port="Gi0/1", remote_port="Gi1/0/24"),
            NeighborInfo(remote_name="edge-sw", local_port="Gi0/2", remote_port="Gi2/0/1"),
        ]

    monkeypatch.setattr(snmp_lldp, "_query_target", fake_query)
    out = await SnmpLldpCollector().collect()
    assert len(out.devices) == 1
    assert out.devices[0].name == "core-sw"
    assert out.devices[0].primary_ip == "10.0.0.1"
    assert [
        (link.local_device, link.remote_device, link.local_port, link.remote_port)
        for link in out.links
    ] == [
        ("core-sw", "agg-sw", "Gi0/1", "Gi1/0/24"),
        ("core-sw", "edge-sw", "Gi0/2", "Gi2/0/1"),
    ]


async def test_collect_handles_pysnmp_missing(monkeypatch):
    monkeypatch.setattr(snmp_lldp, "get_settings", lambda: _settings("10.0.0.1"))

    async def boom(host, spec, *, port, timeout, retries):
        raise ImportError("no pysnmp")

    monkeypatch.setattr(snmp_lldp, "_query_target", boom)
    out = await SnmpLldpCollector().collect()
    assert out.devices == []
    assert any("pysnmp not installed" in note for note in out.notes)


async def test_collect_handles_query_error(monkeypatch):
    monkeypatch.setattr(snmp_lldp, "get_settings", lambda: _settings("10.0.0.1"))

    async def boom(host, spec, *, port, timeout, retries):
        raise RuntimeError("timeout")

    monkeypatch.setattr(snmp_lldp, "_query_target", boom)
    out = await SnmpLldpCollector().collect()
    assert out.devices == []
    assert any("query failed" in note.lower() for note in out.notes)


async def test_collect_runs_targets_in_parallel(monkeypatch):
    monkeypatch.setattr(snmp_lldp, "get_settings", lambda: _settings("10.0.0.1,10.0.0.2"))

    started = {"10.0.0.1": asyncio.Event(), "10.0.0.2": asyncio.Event()}

    async def fake_query(host, spec, *, port, timeout, retries):
        # Each target only completes after seeing the other start: proves concurrency,
        # since a sequential loop would deadlock here.
        started[host].set()
        other = "10.0.0.2" if host == "10.0.0.1" else "10.0.0.1"
        await asyncio.wait_for(started[other].wait(), timeout=1.0)
        return host, []

    monkeypatch.setattr(snmp_lldp, "_query_target", fake_query)
    out = await SnmpLldpCollector().collect()
    assert {d.name for d in out.devices} == {"10.0.0.1", "10.0.0.2"}


async def test_collect_one_target_fails_other_succeeds(monkeypatch):
    monkeypatch.setattr(snmp_lldp, "get_settings", lambda: _settings("10.0.0.1,10.0.0.2"))

    async def fake_query(host, spec, *, port, timeout, retries):
        if host == "10.0.0.1":
            raise RuntimeError("unreachable")
        return "core-sw", []

    monkeypatch.setattr(snmp_lldp, "_query_target", fake_query)
    out = await SnmpLldpCollector().collect()
    assert [d.name for d in out.devices] == ["core-sw"]
    assert any("query failed for 10.0.0.1" in note for note in out.notes)


async def test_collect_v3_passes_v3_auth_spec(monkeypatch):
    monkeypatch.setattr(
        snmp_lldp,
        "get_settings",
        lambda: _settings("10.0.0.1", snmp_v3_user="argus", snmp_v3_auth_key="authpass123"),
    )
    captured: list[SnmpAuthSpec] = []

    async def fake_query(host, spec, *, port, timeout, retries):
        captured.append(spec)
        return "core-sw", []

    monkeypatch.setattr(snmp_lldp, "_query_target", fake_query)
    await SnmpLldpCollector().collect()
    assert captured[0].is_v3
    assert captured[0].v3_user == "argus"
    assert captured[0].v3_auth_key == "authpass123"


async def test_collect_v3_notes_ignored_per_target_community(monkeypatch):
    monkeypatch.setattr(
        snmp_lldp,
        "get_settings",
        lambda: _settings("10.0.0.1:secret", snmp_v3_user="argus"),
    )

    async def fake_query(host, spec, *, port, timeout, retries):
        return "core-sw", []

    monkeypatch.setattr(snmp_lldp, "_query_target", fake_query)
    out = await SnmpLldpCollector().collect()
    assert any("ignored (secret)" in note for note in out.notes)
