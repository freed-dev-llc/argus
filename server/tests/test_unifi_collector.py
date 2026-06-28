"""Tests for the UniFi discovery collector (offline — UniFi API mocked via respx)."""

from __future__ import annotations

import httpx
import respx

from argus.config import Settings
from argus.discovery.vendors.unifi import collector as unifi
from argus.discovery.vendors.unifi.collector import UniFiCollector
from argus.discovery.vendors.unifi.models import role_from_model as _role_from_model
from argus.discovery.vendors.unifi.models import status_from_state as _status_from_state

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


def test_status_from_state_maps_only_known_states():
    """Conservative UniFi-state → NetBox-status mapping; everything else returns None to skip."""
    assert _status_from_state("ONLINE") == "active"
    assert _status_from_state("OFFLINE") == "offline"
    assert _status_from_state("PENDING_ADOPTION") == "staged"
    assert _status_from_state("ADOPTING") == "staged"
    # Case-insensitive on input.
    assert _status_from_state("online") == "active"
    assert _status_from_state("Pending_Adoption") == "staged"
    # Unknown / transient / missing states are never mapped — they skip (leave NetBox alone).
    assert _status_from_state("UPDATING") is None
    assert _status_from_state("PROVISIONING") is None
    assert _status_from_state("GETTING_READY") is None
    assert _status_from_state("WHATEVER") is None
    assert _status_from_state("") is None
    assert _status_from_state(None) is None


def _configured() -> Settings:
    return Settings(
        unifi_url=UNIFI,
        unifi_api_token="tok",
        unifi_site="default",
        unifi_verify_ssl=False,
        _env_file=None,
    )


def _settings(*, site: str) -> Settings:
    """A configured Settings with an explicit UNIFI_SITE (for multi-site tests)."""
    return Settings(
        unifi_url=UNIFI,
        unifi_api_token="tok",
        unifi_site=site,
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
async def test_collect_populates_management(monkeypatch):
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
                    {"name": "sw1", "model": "USW-24-PoE", "ipAddress": "10.0.0.2",
                     "state": "ONLINE", "version": "6.6.55", "serial": "ABC123"},
                    {"name": "ap1", "model": "U6-Pro", "ipAddress": "10.0.0.3"},
                ]
            },
        )
    )
    respx.get(f"{BASE}/sites/s1/clients?limit=200").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    result = await UniFiCollector().collect()

    sw, ap = result.devices
    assert sw.management is not None
    # Raw UniFi "ONLINE" is normalized to the NetBox status token at observe time.
    assert sw.management.status == "active"
    assert sw.management.firmware == "6.6.55"
    assert sw.management.serial == "ABC123"
    # A device with no management-plane fields stays None (nothing learned).
    assert ap.management is None


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


@respx.mock
async def test_collect_topology_from_uplinks(monkeypatch):
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
                    {"id": "agg", "name": "Aggregation", "model": "USW Pro Aggregation", "ipAddress": "10.0.0.2"},
                    {"id": "sw", "name": "Switch", "model": "USW Pro 48", "ipAddress": "10.0.0.3"},
                ]
            },
        )
    )
    respx.get(f"{BASE}/sites/s1/clients?limit=200").mock(return_value=httpx.Response(200, json={"data": []}))
    respx.get(f"{BASE}/sites/s1/devices/agg").mock(return_value=httpx.Response(200, json={"id": "agg", "uplink": {}}))
    respx.get(f"{BASE}/sites/s1/devices/sw").mock(
        return_value=httpx.Response(200, json={"id": "sw", "uplink": {"deviceId": "agg"}})
    )

    result = await UniFiCollector().collect()

    assert len(result.links) == 1
    assert result.links[0].local_device == "Switch"
    assert result.links[0].remote_device == "Aggregation"


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


# --- multi-site discovery (#82) -------------------------------------------------


def _two_sites() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": [
                {"id": "s1", "internalReference": "site-a", "name": "Site A"},
                {"id": "s2", "internalReference": "site-b", "name": "Site B"},
            ]
        },
    )


@respx.mock
async def test_collect_all_sites_aggregates_across_sites(monkeypatch):
    """UNIFI_SITE='*' discovers every site; each device is tagged with its own site."""
    monkeypatch.setattr(unifi, "get_settings", lambda: _settings(site="*"))
    respx.get(f"{BASE}/sites").mock(return_value=_two_sites())
    respx.get(f"{BASE}/sites/s1/devices").mock(
        return_value=httpx.Response(
            200, json={"data": [{"name": "sw-a", "model": "USW-24-PoE", "ipAddress": "10.0.0.2"}]}
        )
    )
    respx.get(f"{BASE}/sites/s1/clients?limit=200").mock(httpx.Response(200, json={"data": []}))
    respx.get(f"{BASE}/sites/s2/devices").mock(
        return_value=httpx.Response(
            200, json={"data": [{"name": "sw-b", "model": "USW-24-PoE", "ipAddress": "10.1.0.2"}]}
        )
    )
    respx.get(f"{BASE}/sites/s2/clients?limit=200").mock(httpx.Response(200, json={"data": []}))

    result = await UniFiCollector().collect()

    by_name = {d.name: d for d in result.devices}
    assert set(by_name) == {"sw-a", "sw-b"}
    assert by_name["sw-a"].site == "Site A"
    assert by_name["sw-b"].site == "Site B"
    assert result.ip_addresses == ["10.0.0.2", "10.1.0.2"]


@respx.mock
async def test_collect_empty_site_means_all(monkeypatch):
    """An empty UNIFI_SITE also means all sites (opt-in multi-site)."""
    monkeypatch.setattr(unifi, "get_settings", lambda: _settings(site=""))
    respx.get(f"{BASE}/sites").mock(return_value=_two_sites())
    respx.get(f"{BASE}/sites/s1/devices").mock(
        httpx.Response(200, json={"data": [{"name": "sw-a", "model": "USW-24", "ipAddress": "10.0.0.2"}]})
    )
    respx.get(f"{BASE}/sites/s1/clients?limit=200").mock(httpx.Response(200, json={"data": []}))
    respx.get(f"{BASE}/sites/s2/devices").mock(
        httpx.Response(200, json={"data": [{"name": "sw-b", "model": "USW-24", "ipAddress": "10.1.0.2"}]})
    )
    respx.get(f"{BASE}/sites/s2/clients?limit=200").mock(httpx.Response(200, json={"data": []}))

    result = await UniFiCollector().collect()
    assert {d.name for d in result.devices} == {"sw-a", "sw-b"}


@respx.mock
async def test_collect_single_site_when_reference_specified(monkeypatch):
    """A specific UNIFI_SITE discovers only the matching site (back-compat); others untouched."""
    monkeypatch.setattr(unifi, "get_settings", lambda: _settings(site="site-b"))
    respx.get(f"{BASE}/sites").mock(return_value=_two_sites())
    respx.get(f"{BASE}/sites/s2/devices").mock(
        httpx.Response(200, json={"data": [{"name": "sw-b", "model": "USW-24", "ipAddress": "10.1.0.2"}]})
    )
    respx.get(f"{BASE}/sites/s2/clients?limit=200").mock(httpx.Response(200, json={"data": []}))
    # s1 endpoints intentionally NOT mocked — must never be called (respx would raise).

    result = await UniFiCollector().collect()

    assert [d.name for d in result.devices] == ["sw-b"]
    assert result.devices[0].site == "Site B"


@respx.mock
async def test_collect_falls_back_to_first_site_when_reference_unmatched(monkeypatch):
    """An unmatched specific reference falls back to the first site (unchanged _pick_site)."""
    monkeypatch.setattr(unifi, "get_settings", lambda: _settings(site="nope"))
    respx.get(f"{BASE}/sites").mock(return_value=_two_sites())
    respx.get(f"{BASE}/sites/s1/devices").mock(
        httpx.Response(200, json={"data": [{"name": "sw-a", "model": "USW-24", "ipAddress": "10.0.0.2"}]})
    )
    respx.get(f"{BASE}/sites/s1/clients?limit=200").mock(httpx.Response(200, json={"data": []}))

    result = await UniFiCollector().collect()

    assert [d.name for d in result.devices] == ["sw-a"]  # first site only
    assert result.devices[0].site == "Site A"


@respx.mock
async def test_collect_topology_links_stay_within_site(monkeypatch):
    """Per-site id maps: an uplink id resolves only within its own site (no cross-site link).

    Site B reuses Site A's device id 'sw' and uplinks to 'agg' — which exists only in Site A.
    A global id map would mis-link B's switch to A's aggregation; per-site keeps it isolated.
    """
    monkeypatch.setattr(unifi, "get_settings", lambda: _settings(site="all"))
    respx.get(f"{BASE}/sites").mock(return_value=_two_sites())
    # Site A: agg + sw, with sw -> agg (resolvable within A).
    respx.get(f"{BASE}/sites/s1/devices").mock(
        httpx.Response(
            200,
            json={"data": [
                {"id": "agg", "name": "Agg-A", "model": "USW Pro Aggregation", "ipAddress": "10.0.0.2"},
                {"id": "sw", "name": "Sw-A", "model": "USW Pro 48", "ipAddress": "10.0.0.3"},
            ]},
        )
    )
    respx.get(f"{BASE}/sites/s1/clients?limit=200").mock(httpx.Response(200, json={"data": []}))
    respx.get(f"{BASE}/sites/s1/devices/agg").mock(httpx.Response(200, json={"id": "agg", "uplink": {}}))
    respx.get(f"{BASE}/sites/s1/devices/sw").mock(
        httpx.Response(200, json={"id": "sw", "uplink": {"deviceId": "agg"}})
    )
    # Site B: only 'sw' (id collides with A); uplinks to 'agg', which does NOT exist in B.
    respx.get(f"{BASE}/sites/s2/devices").mock(
        httpx.Response(
            200, json={"data": [{"id": "sw", "name": "Sw-B", "model": "USW Pro 48", "ipAddress": "10.1.0.3"}]}
        )
    )
    respx.get(f"{BASE}/sites/s2/clients?limit=200").mock(httpx.Response(200, json={"data": []}))
    respx.get(f"{BASE}/sites/s2/devices/sw").mock(
        httpx.Response(200, json={"id": "sw", "uplink": {"deviceId": "agg"}})
    )

    result = await UniFiCollector().collect()

    # Exactly one link, within Site A; Site B's 'agg' uplink can't resolve (no agg in B).
    assert len(result.links) == 1
    assert result.links[0].local_device == "Sw-A"
    assert result.links[0].remote_device == "Agg-A"


@respx.mock
async def test_collect_isolates_a_failing_site(monkeypatch):
    """One site's /devices error is noted and the run continues to the next site."""
    monkeypatch.setattr(unifi, "get_settings", lambda: _settings(site="all"))
    respx.get(f"{BASE}/sites").mock(return_value=_two_sites())
    respx.get(f"{BASE}/sites/s1/devices").mock(httpx.Response(500))  # Site A fails
    respx.get(f"{BASE}/sites/s2/devices").mock(
        httpx.Response(200, json={"data": [{"name": "sw-b", "model": "USW-24", "ipAddress": "10.1.0.2"}]})
    )
    respx.get(f"{BASE}/sites/s2/clients?limit=200").mock(httpx.Response(200, json={"data": []}))

    result = await UniFiCollector().collect()

    assert [d.name for d in result.devices] == ["sw-b"]  # Site B still discovered
    assert any("Site A" in note and "failed" in note.lower() for note in result.notes)
