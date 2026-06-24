"""Tests for the practices SPI, the UniFi example practices, and the evaluate_practices tool."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from argus.discovery.base import DiscoveredDevice, DiscoveryResult
from argus.discovery.practices import PracticeContext, Severity
from argus.discovery.vendors.unifi.practices import DevicesHaveRole, DevicesTrackedInNetBox
from argus.tools import practices_tools


def _ctx(
    devices: Iterable[DiscoveredDevice],
    *,
    netbox_devices: list[dict[str, Any]] | None = None,
    netbox_available: bool = False,
) -> PracticeContext:
    return PracticeContext(
        observed=DiscoveryResult(collector="unifi", devices=list(devices)),
        netbox_devices=netbox_devices or [],
        netbox_available=netbox_available,
    )


def test_device_has_role_flags_only_missing_roles() -> None:
    findings = DevicesHaveRole().evaluate(
        _ctx([DiscoveredDevice(name="sw1", role="switch"), DiscoveredDevice(name="mystery")])
    )
    assert [f.target for f in findings] == ["mystery"]
    assert findings[0].severity == Severity.WARNING
    assert findings[0].practice == "unifi.device-has-role"


def test_device_in_netbox_uses_both_observed_and_netbox() -> None:
    practice = DevicesTrackedInNetBox()

    # No NetBox snapshot -> the practice can't tell, so it stays silent.
    assert practice.evaluate(_ctx([DiscoveredDevice(name="sw1")])) == []

    # With a snapshot: known device passes, unknown device is flagged.
    findings = practice.evaluate(
        _ctx(
            [DiscoveredDevice(name="sw1"), DiscoveredDevice(name="new-ap")],
            netbox_devices=[{"name": "sw1"}],
            netbox_available=True,
        )
    )
    assert [f.target for f in findings] == ["new-ap"]
    assert findings[0].severity == Severity.INFO


async def test_evaluate_practices_tool_runs_pack_rules(monkeypatch) -> None:
    async def fake_collect(self):  # noqa: ANN001 - bound method stand-in
        return DiscoveryResult(
            collector="unifi",
            devices=[
                DiscoveredDevice(name="sw1", role="switch"),
                DiscoveredDevice(name="mystery"),
            ],
        )

    monkeypatch.setattr(
        "argus.discovery.vendors.unifi.collector.UniFiCollector.collect", fake_collect
    )
    monkeypatch.setattr(practices_tools, "_netbox_snapshot", lambda: ([], False))

    out = await practices_tools.evaluate_practices("unifi")

    assert out["collector"] == "unifi"
    assert out["practices_run"] == 2
    assert out["netbox_available"] is False
    # The role-less "mystery" device yields exactly one WARNING finding.
    warnings = [f for f in out["findings"] if f["severity"] == "warning"]
    assert [f["target"] for f in warnings] == ["mystery"]
    assert out["summary"]["by_severity"]["warning"] == 1


async def test_evaluate_practices_unknown_pack() -> None:
    out = await practices_tools.evaluate_practices("does-not-exist")
    assert "error" in out
