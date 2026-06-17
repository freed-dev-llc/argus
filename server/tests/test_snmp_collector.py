"""Tests for the SNMP/LLDP collector (offline — the pysnmp query is mocked)."""

from __future__ import annotations

from argus.config import Settings
from argus.discovery.collectors import snmp_lldp
from argus.discovery.collectors.snmp_lldp import SnmpLldpCollector, _parse_targets


def test_parse_targets():
    assert _parse_targets("10.0.0.1, 10.0.0.2:secret ,", "public") == [
        ("10.0.0.1", "public"),
        ("10.0.0.2", "secret"),
    ]


def _settings(targets: str) -> Settings:
    return Settings(snmp_targets=targets, snmp_community="public", _env_file=None)


async def test_collect_unconfigured(monkeypatch):
    monkeypatch.setattr(snmp_lldp, "get_settings", lambda: _settings(""))
    out = await SnmpLldpCollector().collect()
    assert out.devices == []
    assert any("not configured" in note for note in out.notes)


async def test_collect_maps_devices_and_links(monkeypatch):
    monkeypatch.setattr(snmp_lldp, "get_settings", lambda: _settings("10.0.0.1"))

    async def fake_query(host, community):
        return "core-sw", ["agg-sw", "edge-sw"]

    monkeypatch.setattr(snmp_lldp, "_query_target", fake_query)
    out = await SnmpLldpCollector().collect()
    assert len(out.devices) == 1
    assert out.devices[0].name == "core-sw"
    assert out.devices[0].primary_ip == "10.0.0.1"
    assert [(link.local_device, link.remote_device) for link in out.links] == [
        ("core-sw", "agg-sw"),
        ("core-sw", "edge-sw"),
    ]


async def test_collect_handles_pysnmp_missing(monkeypatch):
    monkeypatch.setattr(snmp_lldp, "get_settings", lambda: _settings("10.0.0.1"))

    async def boom(host, community):
        raise ImportError("no pysnmp")

    monkeypatch.setattr(snmp_lldp, "_query_target", boom)
    out = await SnmpLldpCollector().collect()
    assert any("pysnmp not installed" in note for note in out.notes)


async def test_collect_handles_query_error(monkeypatch):
    monkeypatch.setattr(snmp_lldp, "get_settings", lambda: _settings("10.0.0.1"))

    async def boom(host, community):
        raise RuntimeError("timeout")

    monkeypatch.setattr(snmp_lldp, "_query_target", boom)
    out = await SnmpLldpCollector().collect()
    assert out.devices == []
    assert any("query failed" in note.lower() for note in out.notes)
