"""Tests for the UniFi discovery collector (offline — UniFi API mocked via respx)."""

from __future__ import annotations

import httpx
import respx

from argus.config import Settings
from argus.discovery.collectors import unifi
from argus.discovery.collectors.unifi import UniFiCollector, _role_from_model

UNIFI = "https://unifi.test"
BASE = f"{UNIFI}/proxy/network/integration/v1"


def test_role_inference_handles_full_model_names():
    assert _role_from_model("UniFi Dream Machine PRO SE") == "gateway"
    assert _role_from_model("UCG-Ultra") == "gateway"
    assert _role_from_model("USW Pro 48 PoE") == "switch"
    assert _role_from_model("USW Pro Aggregation") == "switch"
    assert _role_from_model("U6 Pro") == "ap"
    assert _role_from_model("U7 Pro") == "ap"
    assert _role_from_model("Some Random Thing") is None
    assert _role_from_model(None) is None


def _configured() -> Settings:
    return Settings(
        unifi_url=UNIFI,
        unifi_api_token="tok",
        unifi_site="default",
        unifi_verify_ssl=False,
        _env_file=None,
    )


@respx.mock
async def test_collect_maps_devices(monkeypatch):
    monkeypatch.setattr(unifi, "get_settings", _configured)
    respx.get(f"{BASE}/sites").mock(
        return_value=httpx.Response(
            200, json={"data": [{"id": "s1", "internalReference": "default", "name": "Home"}]}
        )
    )
    respx.get(f"{BASE}/sites/s1/devices").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"name": "sw1", "mac": "aa:bb:cc:dd:ee:ff", "model": "USW-24-PoE",
                     "ipAddress": "10.0.0.2", "state": "ONLINE"},
                    {"name": "ap1", "mac": "11:22:33:44:55:66", "model": "U6-Pro",
                     "ipAddress": "10.0.0.3"},
                ]
            },
        )
    )
    respx.get(f"{BASE}/sites/s1/clients?limit=200").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    result = await UniFiCollector().collect()

    assert result.collector == "unifi"
    assert len(result.devices) == 2
    sw, ap = result.devices
    assert sw.name == "sw1"
    assert sw.mac == "aa:bb:cc:dd:ee:ff"
    assert sw.primary_ip == "10.0.0.2"
    assert sw.site == "Home"
    assert sw.role == "switch"
    assert ap.role == "ap"
    assert result.ip_addresses == ["10.0.0.2", "10.0.0.3"]


@respx.mock
async def test_collect_maps_clients(monkeypatch):
    monkeypatch.setattr(unifi, "get_settings", _configured)
    respx.get(f"{BASE}/sites").mock(
        return_value=httpx.Response(
            200, json={"data": [{"id": "s1", "internalReference": "default", "name": "Home"}]}
        )
    )
    respx.get(f"{BASE}/sites/s1/devices").mock(return_value=httpx.Response(200, json={"data": []}))
    respx.get(f"{BASE}/sites/s1/clients?limit=200").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"name": "phone", "macAddress": "de:ad:be:ef:00:01", "ipAddress": "10.0.0.50"},
                    {"name": "laptop", "macAddress": "de:ad:be:ef:00:02", "ipAddress": "10.0.0.51"},
                ]
            },
        )
    )

    result = await UniFiCollector().collect()

    assert len(result.clients) == 2
    phone = result.clients[0]
    assert phone.hostname == "phone"
    assert phone.mac == "de:ad:be:ef:00:01"
    assert phone.ip == "10.0.0.50"
    assert "10.0.0.50" in result.ip_addresses and "10.0.0.51" in result.ip_addresses


@respx.mock
async def test_collect_tolerates_missing_clients_endpoint(monkeypatch):
    monkeypatch.setattr(unifi, "get_settings", _configured)
    respx.get(f"{BASE}/sites").mock(
        return_value=httpx.Response(
            200, json={"data": [{"id": "s1", "internalReference": "default", "name": "Home"}]}
        )
    )
    respx.get(f"{BASE}/sites/s1/devices").mock(
        return_value=httpx.Response(
            200, json={"data": [{"name": "sw1", "model": "USW-24", "ipAddress": "10.0.0.2"}]}
        )
    )
    respx.get(f"{BASE}/sites/s1/clients?limit=200").mock(return_value=httpx.Response(404))

    result = await UniFiCollector().collect()

    # Device discovery still succeeds even though the clients endpoint 404s.
    assert len(result.devices) == 1
    assert result.clients == []
    assert any("clients endpoint unavailable" in note for note in result.notes)


async def test_collect_unconfigured(monkeypatch):
    monkeypatch.setattr(
        unifi, "get_settings", lambda: Settings(unifi_url="", unifi_api_token="", _env_file=None)
    )
    result = await UniFiCollector().collect()
    assert result.devices == []
    assert any("not configured" in note for note in result.notes)


@respx.mock
async def test_collect_handles_api_error(monkeypatch):
    monkeypatch.setattr(unifi, "get_settings", _configured)
    respx.get(f"{BASE}/sites").mock(return_value=httpx.Response(500))
    result = await UniFiCollector().collect()
    assert result.devices == []
    assert any("failed" in note.lower() for note in result.notes)
