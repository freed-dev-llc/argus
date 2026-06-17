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


def test_list_devices_uses_all_without_filters():
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        record = MagicMock()
        record.serialize.return_value = {"name": "sw1", "id": 1}
        api.dcim.devices.all.return_value = [record]

        client = NetBoxClient("https://nb", "tok")
        assert client.list_devices() == [{"name": "sw1", "id": 1}]
        api.dcim.devices.all.assert_called_once()
        api.dcim.devices.filter.assert_not_called()


def test_list_devices_filters_when_given():
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        record = MagicMock()
        record.serialize.return_value = {"name": "sw1"}
        api.dcim.devices.filter.return_value = [record]

        client = NetBoxClient("https://nb", "tok")
        client.list_devices(site="hq", role="switch")
        api.dcim.devices.filter.assert_called_once_with(site="hq", role="switch")
