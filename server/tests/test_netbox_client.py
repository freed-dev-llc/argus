"""Tests for the pynetbox wrapper (offline — pynetbox is mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from argus.config import get_settings
from argus.netbox.client import NetBoxClient, _device_to_dict


@pytest.fixture(autouse=True)
def _isolate_settings_cache():
    """Reset ``get_settings``'s lru_cache around each test so env-var changes never leak."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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


# --- _device_to_dict surfaces device_type + manufacturer (#74) -------------------


def test_device_to_dict_surfaces_device_type_and_manufacturer():
    """The comparable dict surfaces the device_type slug and its nested manufacturer slug."""
    record = MagicMock()
    record.id = 1
    record.name = "sw1"
    record.status = "active"
    record.site = MagicMock(slug="hq")
    record.role = MagicMock(slug="switch")
    record.primary_ip = "10.0.0.2/24"
    record.device_type = MagicMock(slug="usw-24-poe", manufacturer=MagicMock(slug="ubiquiti"))

    out = _device_to_dict(record)
    assert out["device_type"] == "usw-24-poe"
    assert out["manufacturer"] == "ubiquiti"
    # additive — existing keys are preserved for the HTTP API / dashboard consumers
    assert out["name"] == "sw1"
    assert out["site"] == "hq"
    assert out["role"] == "switch"
    assert out["primary_ip"] == "10.0.0.2/24"


def test_device_to_dict_surfaces_serial():
    """The comparable dict surfaces the device serial (ADR-0010 write-back); None when absent."""
    record = MagicMock()
    record.id = 3
    record.name = "sw3"
    record.status = "active"
    record.site = MagicMock(slug="hq")
    record.role = MagicMock(slug="switch")
    record.primary_ip = None
    record.device_type = None
    record.serial = "ABC123XYZ"
    assert _device_to_dict(record)["serial"] == "ABC123XYZ"

    record.serial = None
    assert _device_to_dict(record)["serial"] is None


def test_device_to_dict_handles_missing_device_type():
    """A device with no device_type surfaces ``None`` for both keys (never raises)."""
    record = MagicMock()
    record.id = 2
    record.name = "sw2"
    record.status = "active"
    record.site = MagicMock(slug="hq")
    record.role = MagicMock(slug="switch")
    record.primary_ip = None
    record.device_type = None

    out = _device_to_dict(record)
    assert out["device_type"] is None
    assert out["manufacturer"] is None


# --- shared-instance tenant stamping (#86, ADR-0007 soft isolation) ---------------


def test_ensure_tenant_returns_existing_id():
    """``ensure_tenant`` returns an existing tenant's id without creating one."""
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        api.tenancy.tenants.get.return_value = MagicMock(id=12)
        client = NetBoxClient("https://nb", "tok")
        assert client.ensure_tenant("Acme") == 12
        api.tenancy.tenants.get.assert_called_once_with(slug="acme")
        api.tenancy.tenants.create.assert_not_called()


def test_ensure_tenant_creates_when_missing():
    """``ensure_tenant`` find-or-creates with a name + slug (mirrors ``ensure_manufacturer``)."""
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        api.tenancy.tenants.get.return_value = None
        api.tenancy.tenants.create.return_value = MagicMock(id=13)
        client = NetBoxClient("https://nb", "tok")
        assert client.ensure_tenant("Acme Corp") == 13
        api.tenancy.tenants.create.assert_called_once_with(
            {"name": "Acme Corp", "slug": "acme-corp"}
        )


def test_create_device_stamps_tenant_when_configured(monkeypatch):
    """With ``NETBOX_TENANT`` set, a created device carries the resolved tenant id."""
    monkeypatch.setenv("NETBOX_TENANT", "Acme")
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        api.tenancy.tenants.get.return_value = MagicMock(id=77)
        client = NetBoxClient("https://nb", "tok")
        client.create_device(
            {"name": "sw1", "device_type": 1, "role": 2, "site": 3, "status": "active"}
        )
        assert api.dcim.devices.create.call_args[0][0]["tenant"] == 77


def test_create_device_omits_tenant_when_unconfigured(monkeypatch):
    """Back-compat: with ``NETBOX_TENANT`` unset, the create payload has no ``tenant`` key."""
    monkeypatch.delenv("NETBOX_TENANT", raising=False)
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        client = NetBoxClient("https://nb", "tok")
        client.create_device(
            {"name": "sw1", "device_type": 1, "role": 2, "site": 3, "status": "active"}
        )
        payload = api.dcim.devices.create.call_args[0][0]
        assert "tenant" not in payload
        api.tenancy.tenants.get.assert_not_called()  # unset → tenant never resolved


def test_ensure_site_stamps_tenant_when_configured(monkeypatch):
    """A newly-created supporting site carries the configured tenant."""
    monkeypatch.setenv("NETBOX_TENANT", "Acme")
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        api.tenancy.tenants.get.return_value = MagicMock(id=77)
        api.dcim.sites.get.return_value = None
        api.dcim.sites.create.return_value = MagicMock(id=8)
        client = NetBoxClient("https://nb", "tok")
        assert client.ensure_site("Main Office") == 8
        api.dcim.sites.create.assert_called_once_with(
            {"name": "Main Office", "slug": "main-office", "status": "active", "tenant": 77}
        )


def test_ensure_ip_address_stamps_tenant_when_configured(monkeypatch):
    """A newly-created IPAM IP carries the configured tenant."""
    monkeypatch.setenv("NETBOX_TENANT", "Acme")
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        api.tenancy.tenants.get.return_value = MagicMock(id=77)
        api.ipam.ip_addresses.get.return_value = None
        api.ipam.ip_addresses.create.return_value = MagicMock(id=42)
        client = NetBoxClient("https://nb", "tok")
        assert client.ensure_ip_address("10.0.0.9") == 42
        assert api.ipam.ip_addresses.create.call_args[0][0]["tenant"] == 77


def test_assign_primary_ip_stamps_tenant_on_created_mgmt_ip(monkeypatch):
    """The management IP created inside ``assign_primary_ip`` carries the configured tenant."""
    monkeypatch.setenv("NETBOX_TENANT", "Acme")
    monkeypatch.delenv("RECONCILE_MGMT_INTERFACE", raising=False)
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        api.tenancy.tenants.get.return_value = MagicMock(id=77)
        device = MagicMock(id=10)
        api.dcim.devices.get.return_value = device
        api.dcim.interfaces.get.return_value = None
        api.dcim.interfaces.create.return_value = MagicMock(id=20)
        api.ipam.ip_addresses.get.return_value = None
        api.ipam.ip_addresses.create.return_value = MagicMock(id=30)
        NetBoxClient("https://nb", "tok").assign_primary_ip("sw1", "10.0.0.5")
        assert api.ipam.ip_addresses.create.call_args[0][0]["tenant"] == 77


def test_tenant_lookup_is_cached_across_creates(monkeypatch):
    """A multi-object apply resolves the tenant once (cached on the instance)."""
    monkeypatch.setenv("NETBOX_TENANT", "Acme")
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        api.tenancy.tenants.get.return_value = MagicMock(id=77)
        api.dcim.sites.get.return_value = None
        api.dcim.sites.create.return_value = MagicMock(id=8)
        api.ipam.ip_addresses.get.return_value = None
        api.ipam.ip_addresses.create.return_value = MagicMock(id=9)
        client = NetBoxClient("https://nb", "tok")
        client.ensure_site("Home")
        client.ensure_ip_address("10.0.0.1")
        api.tenancy.tenants.get.assert_called_once()


def test_existing_object_skips_create_branch_and_tenant_lookup(monkeypatch):
    """Create-only: an existing object hits no create branch, so the tenant is never resolved."""
    monkeypatch.setenv("NETBOX_TENANT", "Acme")
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        api.dcim.sites.get.return_value = MagicMock(id=5)  # site already exists
        client = NetBoxClient("https://nb", "tok")
        assert client.ensure_site("Home") == 5
        api.dcim.sites.create.assert_not_called()
        api.tenancy.tenants.get.assert_not_called()


def test_update_device_backfills_tenant_when_unset_and_configured(monkeypatch):
    """An update-triggering device with no tenant gets the configured tenant backfilled."""
    monkeypatch.setenv("NETBOX_TENANT", "Acme")
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        api.tenancy.tenants.get.return_value = MagicMock(id=77)
        record = MagicMock()
        record.tenant = None
        api.dcim.devices.get.return_value = record
        client = NetBoxClient("https://nb", "tok")
        client.update_device("sw1", {"status": "active"})
        payload = record.update.call_args[0][0]
        assert payload["tenant"] == 77
        assert payload["status"] == "active"


def test_update_device_does_not_clobber_existing_tenant(monkeypatch):
    """A device that already carries a tenant is never modified on that field."""
    monkeypatch.setenv("NETBOX_TENANT", "Acme")
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        record = MagicMock()
        record.tenant = MagicMock(id=5)  # already tenanted (not necessarily the configured one)
        api.dcim.devices.get.return_value = record
        client = NetBoxClient("https://nb", "tok")
        client.update_device("sw1", {"status": "active"})
        payload = record.update.call_args[0][0]
        assert "tenant" not in payload
        api.tenancy.tenants.get.assert_not_called()


def test_update_device_omits_tenant_when_unconfigured(monkeypatch):
    """Back-compat: with ``NETBOX_TENANT`` unset, the update payload has no ``tenant`` key."""
    monkeypatch.delenv("NETBOX_TENANT", raising=False)
    with patch("argus.netbox.client.pynetbox") as pnb:
        api = MagicMock()
        pnb.api.return_value = api
        record = MagicMock()
        record.tenant = None
        api.dcim.devices.get.return_value = record
        client = NetBoxClient("https://nb", "tok")
        client.update_device("sw1", {"status": "active"})
        payload = record.update.call_args[0][0]
        assert "tenant" not in payload
        api.tenancy.tenants.get.assert_not_called()
