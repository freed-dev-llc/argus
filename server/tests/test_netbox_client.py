"""Tests for the pynetbox wrapper (offline — pynetbox is mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from argus.config import get_settings
from argus.netbox.client import NetBoxClient


def test_constructs_api_and_sets_verify():
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        NetBoxClient("https://nb", "tok", verify_ssl=False)
        pnb.api.assert_called_once_with("https://nb", token="tok")
        assert api.http_session.verify is False


def _mock_device(name="sw1", site="hq", role="switch", ip="10.0.0.2/24"):
    r = MagicMock()
    r.id = 1
    r.name = name
    r.status = "active"
    r.site = MagicMock(slug=site)
    r.role = MagicMock(slug=role)
    r.primary_ip = ip
    return r


def test_list_devices_resolves_fk_fields():
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        api.dcim.devices.all.return_value = [_mock_device()]

        client = NetBoxClient("https://nb", "tok")
        out = client.list_devices()
        assert out[0]["name"] == "sw1"
        assert out[0]["site"] == "hq"
        assert out[0]["role"] == "switch"
        assert out[0]["primary_ip"] == "10.0.0.2/24"
        api.dcim.devices.all.assert_called_once()
        api.dcim.devices.filter.assert_not_called()


def test_list_devices_filters_when_given():
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        api.dcim.devices.filter.return_value = [_mock_device()]

        client = NetBoxClient("https://nb", "tok")
        client.list_devices(site="hq", role="switch")
        api.dcim.devices.filter.assert_called_once_with(site="hq", role="switch")


def test_ensure_site_returns_existing_id():
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        api.dcim.sites.get.return_value = MagicMock(id=7)
        client = NetBoxClient("https://nb", "tok")
        assert client.ensure_site("Home") == 7
        api.dcim.sites.get.assert_called_once_with(slug="home")
        api.dcim.sites.create.assert_not_called()


def test_ensure_site_creates_when_missing():
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        api.dcim.sites.get.return_value = None
        api.dcim.sites.create.return_value = MagicMock(id=8)
        client = NetBoxClient("https://nb", "tok")
        assert client.ensure_site("Main Office") == 8
        api.dcim.sites.create.assert_called_once_with(
            {"name": "Main Office", "slug": "main-office", "status": "active"}
        )


def test_ensure_device_type_creates_with_manufacturer():
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        api.dcim.device_types.get.return_value = None
        api.dcim.device_types.create.return_value = MagicMock(id=5)
        client = NetBoxClient("https://nb", "tok")
        assert client.ensure_device_type("USW-24-PoE", 3) == 5
        api.dcim.device_types.create.assert_called_once_with(
            {"model": "USW-24-PoE", "slug": "usw-24-poe", "manufacturer": 3}
        )


# --- family-aware primary-IP assignment (#73) -----------------------------------


def _assign_primary_ip(ip: str) -> tuple[MagicMock, MagicMock]:
    """Run ``assign_primary_ip`` against a fully-mocked NetBox; return ``(api, device)``.

    The device, interface, and IP objects are all absent so the create paths run; the
    recorded mock calls survive the ``patch`` context for post-hoc assertions.
    """
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        device = MagicMock(id=10)
        api.dcim.devices.get.return_value = device
        api.dcim.interfaces.get.return_value = None
        api.dcim.interfaces.create.return_value = MagicMock(id=20)
        api.ipam.ip_addresses.get.return_value = None
        api.ipam.ip_addresses.create.return_value = MagicMock(id=30)
        NetBoxClient("https://nb", "tok").assign_primary_ip("sw1", ip)
        return api, device


def test_assign_primary_ipv4_maskless_defaults_32_and_v4_field(monkeypatch):
    """A maskless IPv4 defaults to /32 and lands in ``primary_ip4``."""
    monkeypatch.delenv("RECONCILE_MGMT_INTERFACE", raising=False)
    get_settings.cache_clear()
    api, device = _assign_primary_ip("10.0.0.5")
    assert api.ipam.ip_addresses.create.call_args[0][0]["address"] == "10.0.0.5/32"
    device.update.assert_called_once_with({"primary_ip4": 30})


def test_assign_primary_ipv6_maskless_defaults_128_and_v6_field(monkeypatch):
    """A maskless IPv6 defaults to /128 and lands in ``primary_ip6`` (the actual bug fix)."""
    monkeypatch.delenv("RECONCILE_MGMT_INTERFACE", raising=False)
    get_settings.cache_clear()
    api, device = _assign_primary_ip("2001:db8::1")
    assert api.ipam.ip_addresses.create.call_args[0][0]["address"] == "2001:db8::1/128"
    device.update.assert_called_once_with({"primary_ip6": 30})


def test_assign_primary_ipv4_honors_provided_mask(monkeypatch):
    """A provided IPv4 mask is honored (not overwritten with /32)."""
    monkeypatch.delenv("RECONCILE_MGMT_INTERFACE", raising=False)
    get_settings.cache_clear()
    api, device = _assign_primary_ip("10.0.0.5/24")
    assert api.ipam.ip_addresses.create.call_args[0][0]["address"] == "10.0.0.5/24"
    device.update.assert_called_once_with({"primary_ip4": 30})


def test_assign_primary_ipv6_honors_provided_mask(monkeypatch):
    """A provided IPv6 mask is honored and still routes to ``primary_ip6``."""
    monkeypatch.delenv("RECONCILE_MGMT_INTERFACE", raising=False)
    get_settings.cache_clear()
    api, device = _assign_primary_ip("2001:db8::1/64")
    assert api.ipam.ip_addresses.create.call_args[0][0]["address"] == "2001:db8::1/64"
    device.update.assert_called_once_with({"primary_ip6": 30})


def test_assign_primary_ip_uses_default_mgmt_interface(monkeypatch):
    """With no env override, the interface defaults to ``mgmt``."""
    monkeypatch.delenv("RECONCILE_MGMT_INTERFACE", raising=False)
    get_settings.cache_clear()
    api, _ = _assign_primary_ip("10.0.0.5")
    api.dcim.interfaces.get.assert_called_once_with(device_id=10, name="mgmt")
    assert api.dcim.interfaces.create.call_args[0][0]["name"] == "mgmt"


def test_assign_primary_ip_honors_configured_interface(monkeypatch):
    """``RECONCILE_MGMT_INTERFACE`` overrides the management interface name."""
    monkeypatch.setenv("RECONCILE_MGMT_INTERFACE", "eth0")
    get_settings.cache_clear()
    api, _ = _assign_primary_ip("10.0.0.5")
    api.dcim.interfaces.get.assert_called_once_with(device_id=10, name="eth0")
    assert api.dcim.interfaces.create.call_args[0][0]["name"] == "eth0"


def test_ensure_ip_address_ipv6_defaults_128():
    """``ensure_ip_address`` defaults an IPv6 to /128 (no longer forces /32)."""
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        api.ipam.ip_addresses.get.return_value = None
        api.ipam.ip_addresses.create.return_value = MagicMock(id=42)
        client = NetBoxClient("https://nb", "tok")
        assert client.ensure_ip_address("2001:db8::5") == 42
        assert api.ipam.ip_addresses.create.call_args[0][0]["address"] == "2001:db8::5/128"


def test_ensure_ip_address_ipv4_defaults_32():
    """``ensure_ip_address`` still defaults a maskless IPv4 to /32 (via the family helper)."""
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        api.ipam.ip_addresses.get.return_value = None
        api.ipam.ip_addresses.create.return_value = MagicMock(id=43)
        client = NetBoxClient("https://nb", "tok")
        assert client.ensure_ip_address("10.0.0.9") == 43
        assert api.ipam.ip_addresses.create.call_args[0][0]["address"] == "10.0.0.9/32"
