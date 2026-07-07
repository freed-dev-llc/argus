"""Live integration tests for pfSense/OPNsense discovery.

These tests require lab instances at 192.168.1.92 (OPNsense) and 192.168.1.93 (pfSense),
with corresponding credential files in ~/.secrets/.

Run with: pytest -m live tests/test_pfsense_live.py -v

By default, these tests are skipped (marked @pytest.mark.live). Only run when lab
instances are available and credentials are configured.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from argus.discovery.vendors.pfsense.collector import PfSenseCollector

pytestmark = pytest.mark.live


def _load_creds_file(path: str) -> dict:
    """Load credentials from a JSON file in ~/.secrets/."""
    secret_path = Path.home() / ".secrets" / path
    if not secret_path.exists():
        pytest.skip(f"Credential file not found: {secret_path}")
    with open(secret_path) as f:
        return json.load(f)


@pytest.fixture
def opnsense_creds() -> dict:
    """Load OPNsense lab credentials."""
    return _load_creds_file("lab-opnsense-creds")


@pytest.fixture
def pfsense_creds() -> dict:
    """Load pfSense lab credentials."""
    return _load_creds_file("lab-pfsense-creds")


@pytest.fixture
def snmp_settings() -> dict:
    """Load SNMP lab settings."""
    return _load_creds_file("lab-snmpv2")


@pytest.mark.asyncio
async def test_discover_opnsense_192_168_1_92(opnsense_creds: dict) -> None:
    """Test OPNsense discovery at 192.168.1.92."""
    collector = PfSenseCollector()

    # Create a mock environment for discovery.
    env_vars = {
        "PFSENSE_HOST": "192.168.1.92",
        "PFSENSE_USERNAME": opnsense_creds["username"],
        "PFSENSE_PASSWORD": opnsense_creds["password"],
        "PFSENSE_USE_SNMP": "false",
    }

    from unittest.mock import patch

    with patch.dict(os.environ, env_vars, clear=False):
        result = await collector.collect()

    # Verify result contains devices.
    assert len(result.devices) >= 1, "No devices discovered from OPNsense"

    device = result.devices[0]
    assert device.primary_ip is not None, "Device has no primary IP"
    assert device.manufacturer == "Netgate", f"Unexpected manufacturer: {device.manufacturer}"
    assert device.role == "gateway", f"Unexpected role: {device.role}"

    # Verify the device's primary IP is reachable IPv4 format.
    import ipaddress

    try:
        addr = ipaddress.ip_address(device.primary_ip.split("/")[0])
        assert isinstance(addr, ipaddress.IPv4Address), f"Not IPv4: {device.primary_ip}"
        assert addr.is_private, f"Not private IP: {device.primary_ip}"
    except ValueError as exc:
        pytest.fail(f"Invalid primary IP format: {device.primary_ip}: {exc}")

    # Log discovery result for fixture capture.
    print(f"OPNsense device: {device.name} at {device.primary_ip} (model: {device.model})")
    for note in result.notes:
        print(f"  Note: {note}")


@pytest.mark.asyncio
async def test_discover_pfsense_192_168_1_93(pfsense_creds: dict) -> None:
    """Test pfSense discovery at 192.168.1.93."""
    collector = PfSenseCollector()

    # Create a mock environment for discovery.
    env_vars = {
        "PFSENSE_HOST": "192.168.1.93",
        "PFSENSE_USERNAME": pfsense_creds["username"],
        "PFSENSE_PASSWORD": pfsense_creds["password"],
        "PFSENSE_USE_SNMP": "false",
    }

    from unittest.mock import patch

    with patch.dict(os.environ, env_vars, clear=False):
        result = await collector.collect()

    # Verify result contains devices.
    assert len(result.devices) >= 1, "No devices discovered from pfSense"

    device = result.devices[0]
    assert device.primary_ip is not None, "Device has no primary IP"
    assert device.manufacturer == "Netgate", f"Unexpected manufacturer: {device.manufacturer}"
    assert device.role == "gateway", f"Unexpected role: {device.role}"

    # Verify the device's primary IP is reachable IPv4 format.
    import ipaddress

    try:
        addr = ipaddress.ip_address(device.primary_ip.split("/")[0])
        assert isinstance(addr, ipaddress.IPv4Address), f"Not IPv4: {device.primary_ip}"
        assert addr.is_private, f"Not private IP: {device.primary_ip}"
    except ValueError as exc:
        pytest.fail(f"Invalid primary IP format: {device.primary_ip}: {exc}")

    # Log discovery result for fixture capture.
    print(f"pfSense device: {device.name} at {device.primary_ip} (model: {device.model})")
    for note in result.notes:
        print(f"  Note: {note}")
