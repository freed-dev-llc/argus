"""Tests for the pynetbox wrapper (offline — pynetbox is mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
