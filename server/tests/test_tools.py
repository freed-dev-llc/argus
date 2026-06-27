"""Tests for the agent-facing tools (offline — NetBox client is faked)."""

from __future__ import annotations

from importlib.metadata import version

from argus import server
from argus.config import Settings
from argus.discovery.base import DiscoveredDevice, DiscoveredLink, DiscoveryResult
from argus.tools import discovery_tools, read_tools


class _FakeClient:
    def list_devices(self, site=None, role=None):
        return [{"name": "sw1"}]

    def list_prefixes(self):
        return [{"prefix": "10.0.0.0/24"}]


# --- read tools -----------------------------------------------------------------


async def test_list_devices_ok(monkeypatch):
    monkeypatch.setattr(read_tools, "_get_client", lambda: _FakeClient())
    out = await read_tools.list_devices()
    assert out["count"] == 1
    assert out["devices"][0]["name"] == "sw1"


async def test_list_devices_unconfigured(monkeypatch):
    monkeypatch.setattr(
        read_tools,
        "get_settings",
        lambda: Settings(netbox_url="", netbox_token="", _env_file=None),
    )
    read_tools._client = None
    out = await read_tools.list_devices()
    assert "error" in out
    assert "NETBOX" in out["error"].upper()


# --- discovery tools ------------------------------------------------------------


async def test_list_collectors():
    out = await discovery_tools.list_collectors()
    assert "unifi" in out["collectors"]


async def test_discovery_scan_known_collector():
    out = await discovery_tools.discovery_scan("unifi")
    assert out["collector"] == "unifi"
    assert out["notes"]  # stub leaves an explanatory note


async def test_discovery_scan_unknown_collector():
    out = await discovery_tools.discovery_scan("nope")
    assert "error" in out


class _FakeTopoCollector:
    name = "faketopo"

    async def collect(self):
        return DiscoveryResult(
            collector="faketopo",
            devices=[DiscoveredDevice(name="a", role="switch"), DiscoveredDevice(name="b", role="ap")],
            links=[DiscoveredLink(local_device="b", remote_device="a")],
        )


async def test_network_topology(monkeypatch):
    monkeypatch.setitem(discovery_tools.COLLECTORS, "faketopo", _FakeTopoCollector)
    out = await discovery_tools.network_topology("faketopo")
    assert {n["name"] for n in out["nodes"]} == {"a", "b"}
    assert out["links"] == [{"source": "b", "target": "a"}]


async def test_network_topology_unknown_collector():
    out = await discovery_tools.network_topology("nope")
    assert "error" in out


# --- health tool ----------------------------------------------------------------


async def test_health_reports_version(monkeypatch):
    monkeypatch.setattr(
        server,
        "get_settings",
        lambda: Settings(netbox_url="", netbox_token="", _env_file=None),
    )
    out = await server.health()
    assert out["status"] == "unconfigured"
    assert out["version"] == version("argus-netbox")
