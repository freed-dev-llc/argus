"""Tests for the reconcile engine and reconcile tools (offline — NetBox is faked)."""

from __future__ import annotations

from typing import Any

from argus.discovery.base import DiscoveredDevice, DiscoveryResult
from argus.reconcile.engine import ReconcileChange, ReconcileEngine, ReconcilePlan
from argus.tools import reconcile_tools


class FakeNetBox:
    """Minimal stand-in for NetBoxClient."""

    def __init__(self, devices: list[dict[str, Any]] | None = None) -> None:
        self._devices = devices or []
        self.created: list[dict[str, Any]] = []
        self.updated: list[tuple[str, dict[str, Any]]] = []

    def list_devices(self) -> list[dict[str, Any]]:
        return self._devices

    def create_device(self, data: dict[str, Any]) -> dict[str, Any]:
        self.created.append(data)
        return {**data, "id": 99}

    def update_device(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        self.updated.append((name, data))
        return {"name": name, **data}


def _observed(*devices: DiscoveredDevice) -> DiscoveryResult:
    return DiscoveryResult(collector="unifi", devices=list(devices))


# --- diff -----------------------------------------------------------------------


def test_diff_proposes_create_for_unknown_device():
    plan = ReconcileEngine(FakeNetBox([])).diff(
        _observed(DiscoveredDevice(name="sw1", primary_ip="10.0.0.2", site="Home", role="switch"))
    )
    assert len(plan.changes) == 1
    change = plan.changes[0]
    assert change.action == "create"
    assert change.identifier == "sw1"
    assert change.details["primary_ip"] == "10.0.0.2"


def test_diff_proposes_update_on_ip_drift():
    nb = FakeNetBox([{"name": "sw1", "primary_ip": {"address": "10.0.0.9/24"}}])
    plan = ReconcileEngine(nb).diff(_observed(DiscoveredDevice(name="sw1", primary_ip="10.0.0.2")))
    assert len(plan.changes) == 1
    assert plan.changes[0].action == "update"
    assert plan.changes[0].details["primary_ip"] == {"current": "10.0.0.9", "desired": "10.0.0.2"}


def test_diff_no_change_when_ip_matches():
    nb = FakeNetBox([{"name": "sw1", "primary_ip": {"address": "10.0.0.2/24"}}])
    plan = ReconcileEngine(nb).diff(_observed(DiscoveredDevice(name="sw1", primary_ip="10.0.0.2")))
    assert plan.changes == []


def test_diff_notes_stale_netbox_only_devices():
    plan = ReconcileEngine(FakeNetBox([{"name": "old-sw"}])).diff(_observed())
    assert plan.changes == []
    assert any("old-sw" in note for note in plan.notes)


# --- apply ----------------------------------------------------------------------


def test_apply_is_noop_without_confirm():
    nb = FakeNetBox([])
    plan = ReconcilePlan(changes=[ReconcileChange("update", "device", "sw1", {})])
    result = ReconcileEngine(nb).apply(plan, confirm=False)
    assert result["applied"] is False
    assert nb.updated == []


def test_apply_update_calls_client():
    nb = FakeNetBox([])
    plan = ReconcilePlan(
        changes=[
            ReconcileChange(
                "update", "device", "sw1", {"primary_ip": {"current": "x", "desired": "10.0.0.2"}}
            )
        ]
    )
    result = ReconcileEngine(nb).apply(plan, confirm=True)
    assert nb.updated == [("sw1", {"primary_ip": "10.0.0.2"})]
    assert result["applied_count"] == 1
    assert result["results"][0]["status"] == "updated"


def test_apply_create_skips_without_device_type():
    nb = FakeNetBox([])
    plan = ReconcilePlan(
        changes=[ReconcileChange("create", "device", "sw1", {"name": "sw1", "primary_ip": "10.0.0.2"})]
    )
    result = ReconcileEngine(nb).apply(plan, confirm=True)
    assert result["results"][0]["status"] == "skipped"
    assert nb.created == []


def test_apply_create_with_device_type():
    nb = FakeNetBox([])
    plan = ReconcilePlan(
        changes=[
            ReconcileChange(
                "create", "device", "sw1",
                {"name": "sw1", "device_type": "usw-24", "role": "switch", "site": "home"},
            )
        ]
    )
    result = ReconcileEngine(nb).apply(plan, confirm=True)
    assert len(nb.created) == 1
    assert result["results"][0]["status"] == "created"


def test_apply_captures_per_change_errors():
    class Boom(FakeNetBox):
        def update_device(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("netbox said no")

    plan = ReconcilePlan(
        changes=[ReconcileChange("update", "device", "sw1", {"primary_ip": {"current": "a", "desired": "b"}})]
    )
    result = ReconcileEngine(Boom([])).apply(plan, confirm=True)
    assert result["results"][0]["status"] == "error"
    assert "netbox said no" in result["results"][0]["detail"]


# --- tools ----------------------------------------------------------------------


async def test_drift_report_unconfigured(monkeypatch):
    monkeypatch.setattr(reconcile_tools, "_engine", lambda: None)
    out = await reconcile_tools.drift_report()
    assert "error" in out


async def test_drift_report_returns_changes(monkeypatch):
    monkeypatch.setattr(reconcile_tools, "_engine", lambda: ReconcileEngine(FakeNetBox([])))

    async def fake_observe(_collector):
        return _observed(DiscoveredDevice(name="sw1", primary_ip="10.0.0.2"))

    monkeypatch.setattr(reconcile_tools, "_observe", fake_observe)
    out = await reconcile_tools.drift_report()
    assert out["summary"]["total"] == 1
    assert out["changes"][0]["action"] == "create"


async def test_reconcile_apply_confirmation_flow(monkeypatch):
    nb = FakeNetBox([{"name": "sw1", "primary_ip": {"address": "10.0.0.9/24"}}])
    monkeypatch.setattr(reconcile_tools, "_engine", lambda: ReconcileEngine(nb))

    async def fake_observe(_collector):
        return _observed(DiscoveredDevice(name="sw1", primary_ip="10.0.0.2"))

    monkeypatch.setattr(reconcile_tools, "_observe", fake_observe)

    first = await reconcile_tools.reconcile_apply()
    assert first["confirmation_required"] is True

    confirmed = await reconcile_tools.reconcile_apply(confirm_token=first["confirm_token"])
    assert confirmed["confirmed"] is True
    assert confirmed["applied"] is True
    assert nb.updated == [("sw1", {"primary_ip": "10.0.0.2"})]


async def test_reconcile_apply_no_changes(monkeypatch):
    monkeypatch.setattr(reconcile_tools, "_engine", lambda: ReconcileEngine(FakeNetBox([])))

    async def fake_observe(_collector):
        return _observed()

    monkeypatch.setattr(reconcile_tools, "_observe", fake_observe)
    out = await reconcile_tools.reconcile_apply()
    assert out["applied"] is False
    assert "No changes" in out["message"]


async def test_reconcile_apply_rejects_bad_token(monkeypatch):
    monkeypatch.setattr(reconcile_tools, "_engine", lambda: ReconcileEngine(FakeNetBox([])))
    out = await reconcile_tools.reconcile_apply(confirm_token="bogus")
    assert "error" in out
