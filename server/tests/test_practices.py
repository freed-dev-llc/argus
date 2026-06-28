"""Tests for the practices SPI, the UniFi example practices, and the evaluate_practices tool."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from argus.discovery.base import DeviceManagement, DiscoveredDevice, DiscoveryResult
from argus.discovery.practices import PracticeContext, Severity
from argus.discovery.vendors.unifi.practices import (
    UNIFI_PRACTICES,
    DevicesHavePrimaryIP,
    DevicesHaveRole,
    DevicesHaveSerial,
    DevicesNamed,
    DevicesTrackedInNetBox,
    UniqueDeviceNames,
)
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
    # Devices are clean except for "mystery" having no role, so only DevicesHaveRole fires.
    clean = {"primary_ip": "10.0.0.1", "management": DeviceManagement(serial="S1")}

    async def fake_collect(self):  # noqa: ANN001 - bound method stand-in
        return DiscoveryResult(
            collector="unifi",
            devices=[
                DiscoveredDevice(name="sw1", role="switch", **clean),
                DiscoveredDevice(name="mystery", **clean),
            ],
        )

    monkeypatch.setattr(
        "argus.discovery.vendors.unifi.collector.UniFiCollector.collect", fake_collect
    )
    monkeypatch.setattr(practices_tools, "_netbox_snapshot", lambda: ([], False))

    out = await practices_tools.evaluate_practices("unifi")

    assert out["collector"] == "unifi"
    assert out["practices_run"] == 6
    assert out["netbox_available"] is False
    # The role-less "mystery" device yields exactly one WARNING finding.
    warnings = [f for f in out["findings"] if f["severity"] == "warning"]
    assert [f["target"] for f in warnings] == ["mystery"]
    assert out["summary"]["by_severity"]["warning"] == 1


def test_unifi_pack_surfaces_six_practices() -> None:
    """The pack ships the original two plus the four #83 rules — six total, all reachable."""
    from argus.discovery.vendors.unifi import UNIFI_PACK

    assert len(UNIFI_PRACTICES) == 6
    assert len(UNIFI_PACK.practices) == 6  # reachable via the pack
    ids = {p.id for p in UNIFI_PRACTICES}
    assert {
        "unifi.device-has-primary-ip",
        "unifi.device-has-serial",
        "unifi.unique-device-names",
        "unifi.device-named",
    } <= ids


def test_device_has_primary_ip_flags_missing() -> None:
    findings = DevicesHavePrimaryIP().evaluate(
        _ctx([DiscoveredDevice(name="sw1", primary_ip="10.0.0.1"), DiscoveredDevice(name="ap1")])
    )
    assert [f.target for f in findings] == ["ap1"]
    assert findings[0].severity == Severity.WARNING
    assert findings[0].practice == "unifi.device-has-primary-ip"


def test_device_has_primary_ip_passes_when_present() -> None:
    findings = DevicesHavePrimaryIP().evaluate(
        _ctx([DiscoveredDevice(name="sw1", primary_ip="10.0.0.1")])
    )
    assert findings == []


def test_device_has_serial_flags_missing_and_none_management() -> None:
    findings = DevicesHaveSerial().evaluate(
        _ctx(
            [
                DiscoveredDevice(name="sw1", management=DeviceManagement(serial="ABC123")),
                DiscoveredDevice(name="ap1", management=DeviceManagement(serial=None)),
                DiscoveredDevice(name="ap2"),  # management is None — must be guarded, not raise
            ]
        )
    )
    assert [f.target for f in findings] == ["ap1", "ap2"]
    assert findings[0].severity == Severity.INFO
    assert findings[0].practice == "unifi.device-has-serial"


def test_device_has_serial_passes_when_present() -> None:
    findings = DevicesHaveSerial().evaluate(
        _ctx([DiscoveredDevice(name="sw1", management=DeviceManagement(serial="ABC123"))])
    )
    assert findings == []


def test_unique_device_names_flags_duplicates_case_insensitively() -> None:
    findings = UniqueDeviceNames().evaluate(
        _ctx(
            [
                DiscoveredDevice(name="sw1"),
                DiscoveredDevice(name="SW1"),  # collides with sw1 (lowercased)
                DiscoveredDevice(name="ap1"),
            ]
        )
    )
    assert {f.target for f in findings} == {"sw1", "SW1"}
    assert findings[0].severity == Severity.ERROR
    assert findings[0].practice == "unifi.unique-device-names"


def test_unique_device_names_passes_when_all_unique() -> None:
    findings = UniqueDeviceNames().evaluate(
        _ctx([DiscoveredDevice(name="sw1"), DiscoveredDevice(name="sw2")])
    )
    assert findings == []


def test_device_named_flags_unknown_and_mac_fallbacks() -> None:
    findings = DevicesNamed().evaluate(
        _ctx(
            [
                DiscoveredDevice(name="core-sw-1"),  # real name — passes
                DiscoveredDevice(name="unknown"),  # literal fallback
                DiscoveredDevice(name="aa:bb:cc:dd:ee:ff", mac="AA:BB:CC:DD:EE:FF"),  # name == MAC
            ]
        )
    )
    assert [f.target for f in findings] == ["unknown", "aa:bb:cc:dd:ee:ff"]
    assert findings[0].severity == Severity.WARNING
    assert findings[0].practice == "unifi.device-named"


def test_device_named_passes_for_real_name() -> None:
    findings = DevicesNamed().evaluate(
        _ctx([DiscoveredDevice(name="core-sw-1", mac="AA:BB:CC:DD:EE:FF")])
    )
    assert findings == []


async def test_evaluate_practices_unknown_pack() -> None:
    out = await practices_tools.evaluate_practices("does-not-exist")
    assert "error" in out
