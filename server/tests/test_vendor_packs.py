"""Tests for the vendor-pack registry + host/plugin boundary (ADR-0005)."""

from __future__ import annotations

from argus.discovery.base import Collector
from argus.discovery.collectors import COLLECTORS, SnmpLldpCollector, UniFiCollector
from argus.discovery.vendors import (
    BUILTIN_PACKS,
    VENDOR_PACKS,
    Transport,
    discover_packs,
    vendor_collectors,
)
from argus.discovery.vendors.pack import CLIENTS, DEVICES, TOPOLOGY, VendorPack


def test_unifi_is_a_builtin_pack() -> None:
    pack = VENDOR_PACKS["unifi"]
    assert isinstance(pack, VendorPack)
    assert pack.manufacturer == "Ubiquiti"
    assert pack.transport is Transport.CONTROLLER_API
    assert {DEVICES, CLIENTS, TOPOLOGY} <= pack.capabilities
    assert pack.collector is UniFiCollector
    assert pack in BUILTIN_PACKS


def test_collectors_map_merges_vendor_and_legacy() -> None:
    # vendor packs feed COLLECTORS...
    assert COLLECTORS["unifi"] is UniFiCollector
    assert COLLECTORS["unifi"] is vendor_collectors()["unifi"]
    # ...alongside the directly-registered generic collectors
    assert SnmpLldpCollector.name in COLLECTORS


def test_discover_packs_is_deterministic_and_typed() -> None:
    packs = discover_packs()
    assert "unifi" in packs
    for pack in packs.values():
        assert isinstance(pack, VendorPack)
        assert issubclass(pack.collector, Collector)
