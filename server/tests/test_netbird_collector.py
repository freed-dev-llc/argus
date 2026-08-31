"""Offline tests for group-scoped NetBird management API discovery."""

from __future__ import annotations

import httpx
import pytest
import respx

from argus.config import get_settings
from argus.discovery.vendors.netbird.collector import NetBirdCollector


@pytest.fixture(autouse=True)
def _settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _configure(monkeypatch, *, group: str = "Off-LAN VPS") -> None:
    monkeypatch.setenv("NETBIRD_URL", "https://mesh.example")
    monkeypatch.setenv("NETBIRD_API_TOKEN", "nbp_secret")
    monkeypatch.setenv("NETBIRD_GROUP", group)


@pytest.mark.asyncio
async def test_unconfigured_is_read_only_and_explanatory(monkeypatch):
    monkeypatch.delenv("NETBIRD_URL", raising=False)
    monkeypatch.delenv("NETBIRD_API_TOKEN", raising=False)
    monkeypatch.delenv("NETBIRD_GROUP", raising=False)
    result = await NetBirdCollector().collect()
    assert result.devices == []
    assert "NETBIRD_GROUP" in result.notes[0]
    assert result.device_ownership_tag is None


@pytest.mark.asyncio
@respx.mock
async def test_collects_only_group_peers(monkeypatch):
    _configure(monkeypatch)
    groups = respx.get("https://mesh.example/api/groups").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": "g-offlan", "name": "Off-LAN VPS", "peers": ["p1", "p2"]},
                {"id": "g-all", "name": "All", "peers": ["p1", "p2", "p3"]},
            ],
        )
    )
    peers = respx.get("https://mesh.example/api/peers").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "p1",
                    "name": "mesh.netbird.selfhosted",
                    "ip": "100.119.145.174",
                    "connected": True,
                    "version": "0.59.1",
                },
                {
                    "id": "p2",
                    "hostname": "helios",
                    "ip": "100.119.211.234",
                    "connected": False,
                },
                {"id": "p3", "name": "spark", "ip": "100.119.1.2", "connected": True},
            ],
        )
    )

    result = await NetBirdCollector().collect()

    assert groups.called and peers.called
    assert result.device_ownership_tag == "argus-source-netbird"
    assert [device.name for device in result.devices] == ["mesh", "helios"]
    assert [device.primary_ip for device in result.devices] == [
        "100.119.145.174",
        "100.119.211.234",
    ]
    assert result.devices[0].management is not None
    assert result.devices[0].management.status == "active"
    assert result.devices[0].management.mgmt_interface == "wt0"
    assert result.devices[1].management is not None
    assert result.devices[1].management.status == "offline"
    assert result.devices[0].site is None
    assert result.devices[0].role is None
    assert result.devices[0].model is None


@pytest.mark.asyncio
@respx.mock
async def test_accepts_wrapped_payloads_and_dict_peer_membership(monkeypatch):
    _configure(monkeypatch, group="g-offlan")
    respx.get("https://mesh.example/api/groups").mock(
        return_value=httpx.Response(
            200,
            json={"items": [{"id": "g-offlan", "name": "Other", "peers": [{"id": "p1"}]}]},
        )
    )
    respx.get("https://mesh.example/api/peers").mock(
        return_value=httpx.Response(
            200, json={"results": [{"id": "p1", "name": "reach", "ip": "100.119.95.13"}]}
        )
    )
    result = await NetBirdCollector().collect()
    assert [device.name for device in result.devices] == ["reach"]


@pytest.mark.asyncio
@respx.mock
async def test_missing_group_never_fetches_or_imports_all_peers(monkeypatch):
    _configure(monkeypatch)
    respx.get("https://mesh.example/api/groups").mock(
        return_value=httpx.Response(200, json=[{"id": "g-all", "name": "All", "peers": ["p1"]}])
    )
    peer_route = respx.get("https://mesh.example/api/peers")
    result = await NetBirdCollector().collect()
    assert result.devices == []
    assert not peer_route.called
    assert "was not found" in result.notes[0]
    assert result.device_ownership_tag is None


@pytest.mark.asyncio
@respx.mock
async def test_api_error_becomes_note(monkeypatch):
    _configure(monkeypatch)
    respx.get("https://mesh.example/api/groups").mock(return_value=httpx.Response(401))
    result = await NetBirdCollector().collect()
    assert result.devices == []
    assert result.notes[0].startswith("NetBird API request failed:")
    assert result.device_ownership_tag is None


@pytest.mark.asyncio
@respx.mock
async def test_optional_defaults_enable_reconcile_bootstrap(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("NETBIRD_SITE", "Default")
    monkeypatch.setenv("NETBIRD_ROLE", "Application Host")
    monkeypatch.setenv("NETBIRD_MODEL", "Cloud VPS")
    monkeypatch.setenv("NETBIRD_MANUFACTURER", "Hostinger")
    respx.get("https://mesh.example/api/groups").mock(
        return_value=httpx.Response(
            200, json=[{"id": "g-offlan", "name": "Off-LAN VPS", "peers": ["p1"]}]
        )
    )
    respx.get("https://mesh.example/api/peers").mock(
        return_value=httpx.Response(
            200, json=[{"id": "p1", "name": "amp", "ip": "100.119.131.146"}]
        )
    )
    result = await NetBirdCollector().collect()
    device = result.devices[0]
    assert (device.site, device.role, device.model, device.manufacturer) == (
        "Default",
        "Application Host",
        "Cloud VPS",
        "Hostinger",
    )
