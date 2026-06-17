"""Tests for the agent-facing tools (offline — NetBox client is faked)."""

from __future__ import annotations

from argus.config import Settings
from argus.tools import discovery_tools, read_tools, reconcile_tools


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


# --- reconcile tools ------------------------------------------------------------


async def test_drift_report_is_empty_stub():
    out = await reconcile_tools.drift_report()
    assert out["summary"]["total"] == 0


async def test_reconcile_apply_requires_confirmation():
    first = await reconcile_tools.reconcile_apply()
    assert first["confirmation_required"] is True

    confirmed = await reconcile_tools.reconcile_apply(confirm_token=first["confirm_token"])
    assert confirmed["confirmed"] is True


async def test_reconcile_apply_rejects_bad_token():
    out = await reconcile_tools.reconcile_apply(confirm_token="bogus")
    assert "error" in out
