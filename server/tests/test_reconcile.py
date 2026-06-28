"""Tests for the reconcile engine and reconcile tools (offline — NetBox is faked)."""

from __future__ import annotations

from typing import Any

from argus.discovery.base import (
    DeviceManagement,
    DiscoveredClient,
    DiscoveredDevice,
    DiscoveryResult,
)
from argus.reconcile.engine import (
    DeviceTypeIntent,
    ReconcileChange,
    ReconcileEngine,
    ReconcilePlan,
)
from argus.tools import reconcile_tools


class FakeNetBox:
    """Minimal stand-in for NetBoxClient, recording calls and returning fake ids."""

    def __init__(
        self,
        devices: list[dict[str, Any]] | None = None,
        ips: list[dict[str, Any]] | None = None,
    ) -> None:
        self._devices = devices or []
        self._ips = ips or []
        self.created: list[dict[str, Any]] = []
        self.updated: list[tuple[str, dict[str, Any]]] = []
        self.ensured: list[tuple[Any, ...]] = []
        self.primary_ips: list[tuple[str, str]] = []
        self.ensured_ips: list[tuple[str, str]] = []

    def list_devices(self) -> list[dict[str, Any]]:
        return self._devices

    def list_ip_addresses(self) -> list[dict[str, Any]]:
        return self._ips

    def ensure_ip_address(self, address: str, description: str = "") -> int:
        self.ensured_ips.append((address, description))
        return 50

    def create_device(self, data: dict[str, Any]) -> dict[str, Any]:
        self.created.append(data)
        return {**data, "id": 99}

    def update_device(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        self.updated.append((name, data))
        return {"name": name, **data}

    def ensure_site(self, name: str) -> int:
        self.ensured.append(("site", name))
        return 1

    def ensure_role(self, name: str) -> int:
        self.ensured.append(("role", name))
        return 2

    def ensure_manufacturer(self, name: str) -> int:
        self.ensured.append(("manufacturer", name))
        return 3

    def ensure_device_type(self, model: str, manufacturer_id: int) -> int:
        self.ensured.append(("device_type", model, manufacturer_id))
        return 4

    def assign_primary_ip(self, device_name: str, ip: str, interface_name: str = "mgmt") -> None:
        self.primary_ips.append((device_name, ip))


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


def test_diff_proposes_update_on_site_drift():
    nb = FakeNetBox([{"name": "sw1", "site": {"slug": "old-site"}}])
    plan = ReconcileEngine(nb).diff(_observed(DiscoveredDevice(name="sw1", site="Home")))
    assert plan.changes[0].details["site"] == {"current": "old-site", "desired": "Home"}


def test_diff_no_change_when_everything_matches():
    nb = FakeNetBox([{"name": "sw1", "primary_ip": {"address": "10.0.0.2/24"}, "site": {"slug": "home"}}])
    plan = ReconcileEngine(nb).diff(
        _observed(DiscoveredDevice(name="sw1", primary_ip="10.0.0.2", site="home"))
    )
    assert plan.changes == []


def test_diff_notes_stale_netbox_only_devices():
    plan = ReconcileEngine(FakeNetBox([{"name": "old-sw"}])).diff(_observed())
    assert plan.changes == []
    assert any("old-sw" in note for note in plan.notes)


def test_diff_proposes_ip_create_for_new_client():
    obs = DiscoveryResult(
        collector="unifi", clients=[DiscoveredClient(ip="10.0.0.50", hostname="phone")]
    )
    plan = ReconcileEngine(FakeNetBox([], ips=[])).diff(obs)
    ip_changes = [c for c in plan.changes if c.object_type == "ip_address"]
    assert len(ip_changes) == 1
    assert ip_changes[0].action == "create"
    assert ip_changes[0].identifier == "10.0.0.50"
    assert ip_changes[0].details["description"] == "phone"


def test_diff_skips_existing_client_ip():
    nb = FakeNetBox([], ips=[{"address": "10.0.0.50/24"}])
    obs = DiscoveryResult(collector="unifi", clients=[DiscoveredClient(ip="10.0.0.50")])
    plan = ReconcileEngine(nb).diff(obs)
    assert [c for c in plan.changes if c.object_type == "ip_address"] == []


# --- apply ----------------------------------------------------------------------


def test_apply_is_noop_without_confirm():
    nb = FakeNetBox([])
    plan = ReconcilePlan(changes=[ReconcileChange("update", "device", "sw1", {})])
    result = ReconcileEngine(nb).apply(plan, confirm=False)
    assert result["applied"] is False
    assert nb.updated == []


def test_apply_create_persists_with_resolved_fks():
    nb = FakeNetBox([])
    plan = ReconcilePlan(
        changes=[
            ReconcileChange(
                "create", "device", "sw1",
                {
                    "name": "sw1", "site": "Home", "role": "switch",
                    "model": "USW-24-PoE", "manufacturer": "Ubiquiti", "primary_ip": "10.0.0.2",
                },
            )
        ]
    )
    result = ReconcileEngine(nb).apply(plan, confirm=True)
    assert result["results"][0]["status"] == "created"
    assert len(nb.created) == 1
    created = nb.created[0]
    assert created == {"name": "sw1", "device_type": 4, "role": 2, "site": 1, "status": "active"}
    assert nb.primary_ips == [("sw1", "10.0.0.2")]


def test_apply_create_skips_without_required_fields():
    nb = FakeNetBox([])
    plan = ReconcilePlan(
        changes=[ReconcileChange("create", "device", "sw1", {"name": "sw1", "primary_ip": "10.0.0.2"})]
    )
    result = ReconcileEngine(nb).apply(plan, confirm=True)
    assert result["results"][0]["status"] == "skipped"
    assert nb.created == []


def test_apply_update_resolves_site_and_assigns_ip():
    nb = FakeNetBox([])
    plan = ReconcilePlan(
        changes=[
            ReconcileChange(
                "update", "device", "sw1",
                {
                    "site": {"current": "old", "desired": "Home"},
                    "primary_ip": {"current": "10.0.0.9", "desired": "10.0.0.2"},
                },
            )
        ]
    )
    result = ReconcileEngine(nb).apply(plan, confirm=True)
    assert result["results"][0]["status"] == "updated"
    assert nb.updated == [("sw1", {"site": 1})]
    assert nb.primary_ips == [("sw1", "10.0.0.2")]


def test_apply_creates_ip_address():
    nb = FakeNetBox([])
    plan = ReconcilePlan(
        changes=[
            ReconcileChange(
                "create", "ip_address", "10.0.0.50",
                {"address": "10.0.0.50", "description": "phone"},
            )
        ]
    )
    result = ReconcileEngine(nb).apply(plan, confirm=True)
    assert result["results"][0]["status"] == "created"
    assert nb.ensured_ips == [("10.0.0.50", "phone")]


def test_apply_captures_per_change_errors():
    class Boom(FakeNetBox):
        def assign_primary_ip(self, device_name: str, ip: str, interface_name: str = "mgmt") -> None:
            raise RuntimeError("netbox said no")

    plan = ReconcilePlan(
        changes=[ReconcileChange("update", "device", "sw1", {"primary_ip": {"current": "a", "desired": "b"}})]
    )
    result = ReconcileEngine(Boom([])).apply(plan, confirm=True)
    assert result["results"][0]["status"] == "error"
    assert "netbox said no" in result["results"][0]["detail"]


# --- device_type / manufacturer drift (#74) -------------------------------------


def test_diff_proposes_update_on_device_type_and_manufacturer_drift():
    """A different observed model + manufacturer is detected as update-drift."""
    nb = FakeNetBox([{"name": "sw1", "device_type": "usw-24-poe", "manufacturer": "ubiquiti"}])
    plan = ReconcileEngine(nb).diff(
        _observed(DiscoveredDevice(name="sw1", model="USW-48-PoE", manufacturer="MikroTik"))
    )
    assert len(plan.changes) == 1
    change = plan.changes[0]
    assert change.action == "update"
    assert change.details["device_type"]["desired"] == "USW-48-PoE"
    assert change.details["manufacturer"]["desired"] == "MikroTik"


def test_diff_no_drift_when_model_and_manufacturer_match_slug_normalized():
    """Free-text observed model/mfr matching the NetBox slugs is not phantom drift."""
    nb = FakeNetBox([{"name": "sw1", "device_type": "usw-24-poe", "manufacturer": "ubiquiti"}])
    plan = ReconcileEngine(nb).diff(
        _observed(DiscoveredDevice(name="sw1", model="USW-24-PoE", manufacturer="Ubiquiti"))
    )
    assert plan.changes == []


def test_diff_model_only_drift_reports_only_device_type():
    """Model-only drift reports just device_type; the matching manufacturer is not phantom drift.

    The full observed (model, manufacturer) pair rides on the apply-only resolution channel —
    never the reported deltas — so the drift report shows no case-only/no-op manufacturer entry.
    """
    nb = FakeNetBox([{"name": "sw1", "device_type": "usw-24-poe", "manufacturer": "ubiquiti"}])
    plan = ReconcileEngine(nb).diff(
        _observed(DiscoveredDevice(name="sw1", model="USW-48-PoE", manufacturer="Ubiquiti"))
    )
    change = plan.changes[0]
    assert set(change.details) == {"device_type"}  # manufacturer (slug-equal) is NOT reported
    assert change.details["device_type"]["desired"] == "USW-48-PoE"
    assert change.device_type_resolution == DeviceTypeIntent(model="USW-48-PoE", manufacturer="Ubiquiti")


def test_diff_no_op_manufacturer_never_appears_in_reported_deltas():
    """When observed manufacturer equals the stored slug, no manufacturer delta is reported."""
    nb = FakeNetBox([{"name": "sw1", "device_type": "usw-24-poe", "manufacturer": "ubiquiti"}])
    plan = ReconcileEngine(nb).diff(
        _observed(DiscoveredDevice(name="sw1", model="USW-48-PoE", manufacturer="ubiquiti"))
    )
    change = plan.changes[0]
    assert "manufacturer" not in change.details  # no `ubiquiti -> ubiquiti` no-op delta


def test_apply_update_resolves_device_type_fk_jointly():
    """Apply resolves the model + manufacturer intent into a single device_type FK write."""
    nb = FakeNetBox([])
    plan = ReconcilePlan(
        changes=[
            ReconcileChange(
                "update", "device", "sw1",
                {
                    "device_type": {"current": "usw-24-poe", "desired": "USW-48-PoE"},
                    "manufacturer": {"current": "ubiquiti", "desired": "MikroTik"},
                },
                device_type_resolution=DeviceTypeIntent(model="USW-48-PoE", manufacturer="MikroTik"),
            )
        ]
    )
    result = ReconcileEngine(nb).apply(plan, confirm=True)
    assert result["results"][0]["status"] == "updated"
    assert ("manufacturer", "MikroTik") in nb.ensured
    assert ("device_type", "USW-48-PoE", 3) in nb.ensured
    assert nb.updated == [("sw1", {"device_type": 4})]


def test_apply_model_only_drift_resolves_under_real_manufacturer():
    """On model-only drift, apply resolves the device_type under the real mfr — not 'Unknown'."""
    nb = FakeNetBox([])
    plan = ReconcilePlan(
        changes=[
            ReconcileChange(
                "update", "device", "sw1",
                {"device_type": {"current": "usw-24-poe", "desired": "USW-48-PoE"}},
                device_type_resolution=DeviceTypeIntent(model="USW-48-PoE", manufacturer="Ubiquiti"),
            )
        ]
    )
    result = ReconcileEngine(nb).apply(plan, confirm=True)
    assert result["results"][0]["status"] == "updated"
    assert ("manufacturer", "Ubiquiti") in nb.ensured  # real manufacturer, not "Unknown"
    assert nb.updated == [("sw1", {"device_type": 4})]


def test_diff_manufacturer_only_no_model_reports_drift_with_no_resolution():
    """Manufacturer drift with no observed model is reported but carries no apply intent."""
    nb = FakeNetBox([{"name": "sw1", "device_type": "usw-24-poe", "manufacturer": "ubiquiti"}])
    plan = ReconcileEngine(nb).diff(
        _observed(DiscoveredDevice(name="sw1", manufacturer="MikroTik"))  # model is None
    )
    change = plan.changes[0]
    assert set(change.details) == {"manufacturer"}
    assert change.device_type_resolution is None


def test_apply_manufacturer_only_no_model_is_skipped_not_updated():
    """An unresolvable manufacturer-only drift returns honest 'skipped' and writes nothing."""
    nb = FakeNetBox([])
    plan = ReconcilePlan(
        changes=[
            ReconcileChange(
                "update", "device", "sw1",
                {"manufacturer": {"current": "ubiquiti", "desired": "MikroTik"}},
                device_type_resolution=None,  # no observed model → nothing resolvable
            )
        ]
    )
    result = ReconcileEngine(nb).apply(plan, confirm=True)
    assert result["results"][0]["status"] == "skipped"
    assert nb.updated == []
    assert nb.ensured == []


def test_apply_update_site_only_does_not_resolve_device_type():
    """A site-only drift updates site and never touches device_type (behavior unchanged)."""
    nb = FakeNetBox([])
    plan = ReconcilePlan(
        changes=[ReconcileChange("update", "device", "sw1", {"site": {"current": "old", "desired": "Home"}})]
    )
    ReconcileEngine(nb).apply(plan, confirm=True)
    assert nb.updated == [("sw1", {"site": 1})]
    assert not any(entry[0] == "device_type" for entry in nb.ensured)


# --- serial drift (#119, ADR-0010 management-plane write-back) -------------------


def test_diff_proposes_update_on_serial_drift():
    """A differing observed management.serial is detected as update-drift."""
    nb = FakeNetBox([{"name": "sw1", "serial": "OLD999"}])
    plan = ReconcileEngine(nb).diff(
        _observed(DiscoveredDevice(name="sw1", management=DeviceManagement(serial="NEW123")))
    )
    assert len(plan.changes) == 1
    change = plan.changes[0]
    assert change.action == "update"
    assert change.details["serial"] == {"current": "OLD999", "desired": "NEW123"}


def test_diff_no_serial_drift_when_equal():
    """An equal observed serial is not drift."""
    nb = FakeNetBox([{"name": "sw1", "serial": "ABC123"}])
    plan = ReconcileEngine(nb).diff(
        _observed(DiscoveredDevice(name="sw1", management=DeviceManagement(serial="ABC123")))
    )
    assert plan.changes == []


def test_diff_no_serial_drift_when_management_absent():
    """No management sub-object → observed serial is None → no drift (NetBox left alone)."""
    nb = FakeNetBox([{"name": "sw1", "serial": "ABC123"}])
    plan = ReconcileEngine(nb).diff(_observed(DiscoveredDevice(name="sw1")))
    assert plan.changes == []


def test_diff_no_serial_drift_when_observed_serial_none():
    """management present but serial None → observed serial None → no drift."""
    nb = FakeNetBox([{"name": "sw1", "serial": "ABC123"}])
    plan = ReconcileEngine(nb).diff(
        _observed(DiscoveredDevice(name="sw1", management=DeviceManagement(serial=None)))
    )
    assert plan.changes == []


def test_apply_update_writes_serial_as_plain_field():
    """Apply writes serial directly via update_device — no FK resolution."""
    nb = FakeNetBox([])
    plan = ReconcilePlan(
        changes=[
            ReconcileChange(
                "update", "device", "sw1",
                {"serial": {"current": "OLD999", "desired": "NEW123"}},
            )
        ]
    )
    result = ReconcileEngine(nb).apply(plan, confirm=True)
    assert result["results"][0]["status"] == "updated"
    assert nb.updated == [("sw1", {"serial": "NEW123"})]
    assert nb.ensured == []  # plain field — no ensure_* FK resolution


def test_apply_update_serial_with_site_writes_both():
    """Serial coexists with an existing-field drift; both land in one update_device call."""
    nb = FakeNetBox([])
    plan = ReconcilePlan(
        changes=[
            ReconcileChange(
                "update", "device", "sw1",
                {
                    "site": {"current": "old", "desired": "Home"},
                    "serial": {"current": "OLD", "desired": "NEW"},
                },
            )
        ]
    )
    result = ReconcileEngine(nb).apply(plan, confirm=True)
    assert result["results"][0]["status"] == "updated"
    assert nb.updated == [("sw1", {"site": 1, "serial": "NEW"})]


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
    assert nb.primary_ips == [("sw1", "10.0.0.2")]


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
