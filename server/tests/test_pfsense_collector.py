"""Offline tests for the pfSense/OPNsense collector.

These tests verify parsing logic and graceful degradation.
Live tests (requiring lab instances) are in test_pfsense_live.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from argus.discovery.vendors.pfsense.collector import PfSenseCollector
from argus.discovery.vendors.pfsense.models import role_from_model

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "pfsense"


# Custom exceptions for mocking asyncssh
class MockPermissionDenied(Exception):
    """Mock asyncssh.PermissionDenied."""


class MockHostKeyNotVerifiable(Exception):
    """Mock asyncssh.HostKeyNotVerifiable."""


class AsyncContextManager:
    """Helper for mocking async context managers."""

    def __init__(self, obj):
        self.obj = obj

    async def __aenter__(self):
        return self.obj

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


def test_role_from_model_recognizes_gateway_models() -> None:
    """Test that role_from_model returns 'gateway' for pfSense/OPNsense models."""
    assert role_from_model("SG-5100") == "gateway"
    assert role_from_model("SG-3100") == "gateway"
    assert role_from_model("pfSense") == "gateway"
    assert role_from_model("OPNsense") == "gateway"
    assert role_from_model("generic") is None
    assert role_from_model(None) is None


def test_extract_primary_ip_finds_first_private_ip() -> None:
    """Test that _extract_primary_ip returns the first private, non-loopback IP."""
    with open(FIXTURES_DIR / "ssh_ifconfig_output.txt") as f:
        ifconfig_output = f.read()

    primary_ip = PfSenseCollector._extract_primary_ip(ifconfig_output)
    # Should find 192.168.1.1 from em0 (first private, non-loopback, non-link-local).
    assert primary_ip == "192.168.1.1"


def test_extract_primary_ip_skips_loopback() -> None:
    """Test that _extract_primary_ip skips loopback (127.0.0.1)."""
    output = """
lo0: flags=8049<UP,LOOPBACK,RUNNING,SIMPLEX> metric 0 mtu 16384
	inet 127.0.0.1 netmask 0xff000000
em0: flags=8843<UP,BROADCAST,RUNNING,SIMPLEX,MULTICAST> metric 0 mtu 1500
	inet 192.168.1.1 netmask 0xffffff00 broadcast 192.168.1.255
"""
    primary_ip = PfSenseCollector._extract_primary_ip(output)
    assert primary_ip == "192.168.1.1"


def test_extract_primary_ip_skips_link_local() -> None:
    """Test that _extract_primary_ip skips link-local addresses."""
    output = """
em0: flags=8843<UP,BROADCAST,RUNNING,SIMPLEX,MULTICAST> metric 0 mtu 1500
	inet 169.254.1.1 netmask 0xffff0000
em1: flags=8843<UP,BROADCAST,RUNNING,SIMPLEX,MULTICAST> metric 0 mtu 1500
	inet 192.168.1.1 netmask 0xffffff00
"""
    primary_ip = PfSenseCollector._extract_primary_ip(output)
    # Should skip 169.254.1.1 (link-local) and return 192.168.1.1.
    assert primary_ip == "192.168.1.1"


@pytest.mark.asyncio
async def test_collect_unconfigured() -> None:
    """Test that collect returns gracefully when not configured."""
    collector = PfSenseCollector()

    # Ensure env vars are not set.
    env = {
        "PFSENSE_HOST": "",
        "PFSENSE_USERNAME": "",
        "PFSENSE_PASSWORD": "",
    }

    with patch.dict(os.environ, env, clear=False):
        result = await collector.collect()

    assert result.devices == []
    assert any("not configured" in note for note in result.notes)


@pytest.mark.asyncio
async def test_collect_missing_credential_file() -> None:
    """Test that collect handles missing credential files gracefully."""
    collector = PfSenseCollector()

    env = {
        "PFSENSE_HOST": "192.168.1.92",
        "PFSENSE_USERNAME": "~/.secrets/nonexistent-file:username",
        "PFSENSE_PASSWORD": "password",
    }

    with patch.dict(os.environ, env, clear=False):
        result = await collector.collect()

    assert result.devices == []
    assert any("credential file not found" in note for note in result.notes)


@pytest.mark.asyncio
async def test_collect_via_ssh_success(monkeypatch) -> None:
    """Test SSH collection with mocked asyncssh.connect."""
    collector = PfSenseCollector()

    # Load fixture data.
    with open(FIXTURES_DIR / "ssh_show_version_sg5100.txt") as f:
        version_output = f.read()
    with open(FIXTURES_DIR / "ssh_ifconfig_output.txt") as f:
        ifconfig_output = f.read()

    # Mock the connection object.
    mock_conn = MagicMock()

    # Set up responses for different commands.
    async def mock_run(cmd, **kwargs):
        result = MagicMock()
        if cmd == "opnsense-version":
            raise Exception("opnsense-version not available (pfSense system)")
        elif cmd == "show version":
            result.stdout = version_output
        elif cmd == "cat /etc/version":
            raise Exception("File not found")
        elif cmd == "cat /etc/os-release":
            raise Exception("File not found")
        elif cmd == "cat /etc/platform":
            result.stdout = "pfSense"
        elif cmd == "hostname":
            result.stdout = "pfsense-gw1"
        elif cmd == "ifconfig":
            result.stdout = ifconfig_output
        else:
            raise Exception(f"Unexpected command: {cmd}")
        return result

    mock_conn.run = mock_run

    # Create a mock async context manager for connect().
    def mock_connect(*args, **kwargs):
        return AsyncContextManager(mock_conn)

    # Create a mock asyncssh module with needed exception types.
    mock_asyncssh_module = MagicMock()
    mock_asyncssh_module.PermissionDenied = MockPermissionDenied
    mock_asyncssh_module.HostKeyNotVerifiable = MockHostKeyNotVerifiable
    mock_asyncssh_module.connect = mock_connect

    monkeypatch.setitem(sys.modules, "asyncssh", mock_asyncssh_module)

    info = await collector._collect_via_ssh("192.168.1.92", "admin", "password")

    assert info is not None
    assert info["hostname"] == "pfsense-gw1"
    assert info["model"] == "SG-5100"
    assert info["firmware_version"] == "pfSense 2.7.0-RELEASE (SG-5100)"
    assert info["primary_ip"] == "192.168.1.1"


@pytest.mark.asyncio
async def test_collect_via_ssh_no_hostname(monkeypatch) -> None:
    """Test SSH collection when hostname command fails."""
    collector = PfSenseCollector()

    with open(FIXTURES_DIR / "ssh_show_version_sg5100.txt") as f:
        version_output = f.read()
    with open(FIXTURES_DIR / "ssh_ifconfig_output.txt") as f:
        ifconfig_output = f.read()

    mock_conn = MagicMock()

    async def mock_run(cmd, **kwargs):
        result = MagicMock()
        if cmd == "opnsense-version":
            raise Exception("opnsense-version not available")
        elif cmd == "show version":
            result.stdout = version_output
        elif cmd == "cat /etc/version":
            raise Exception("File not found")
        elif cmd == "cat /etc/os-release":
            raise Exception("File not found")
        elif cmd == "cat /etc/platform":
            result.stdout = "pfSense"
        elif cmd == "hostname":
            raise Exception("hostname command failed")
        elif cmd == "ifconfig":
            result.stdout = ifconfig_output
        else:
            raise Exception(f"Unexpected command: {cmd}")
        return result

    mock_conn.run = mock_run

    def mock_connect(*args, **kwargs):
        return AsyncContextManager(mock_conn)

    mock_asyncssh_module = MagicMock()
    mock_asyncssh_module.PermissionDenied = MockPermissionDenied
    mock_asyncssh_module.HostKeyNotVerifiable = MockHostKeyNotVerifiable
    mock_asyncssh_module.connect = mock_connect

    monkeypatch.setitem(sys.modules, "asyncssh", mock_asyncssh_module)

    info = await collector._collect_via_ssh("192.168.1.92", "admin", "password")

    # Hostname should be missing, but model and firmware should be present.
    assert info is not None
    assert "hostname" not in info
    assert info["model"] == "SG-5100"
    assert info["firmware_version"] == "pfSense 2.7.0-RELEASE (SG-5100)"
    assert info["primary_ip"] == "192.168.1.1"


@pytest.mark.asyncio
async def test_collect_via_ssh_fallback_cat_version(monkeypatch) -> None:
    """Test SSH collection falls back to 'cat /etc/version' when 'show version' fails."""
    collector = PfSenseCollector()

    with open(FIXTURES_DIR / "ssh_ifconfig_output.txt") as f:
        ifconfig_output = f.read()

    mock_conn = MagicMock()

    async def mock_run(cmd, **kwargs):
        result = MagicMock()
        if cmd == "opnsense-version":
            raise Exception("opnsense-version not available")
        elif cmd == "show version":
            raise Exception("show version not available")
        elif cmd == "cat /etc/version":
            result.stdout = "OPNsense 24.7.1 (generic)"
        elif cmd == "cat /etc/os-release":
            raise Exception("File not found")
        elif cmd == "cat /etc/platform":
            raise Exception("File not found")
        elif cmd == "hostname":
            result.stdout = "opnsense-gw"
        elif cmd == "ifconfig":
            result.stdout = ifconfig_output
        else:
            raise Exception(f"Unexpected command: {cmd}")
        return result

    mock_conn.run = mock_run

    def mock_connect(*args, **kwargs):
        return AsyncContextManager(mock_conn)

    mock_asyncssh_module = MagicMock()
    mock_asyncssh_module.PermissionDenied = MockPermissionDenied
    mock_asyncssh_module.HostKeyNotVerifiable = MockHostKeyNotVerifiable
    mock_asyncssh_module.connect = mock_connect

    monkeypatch.setitem(sys.modules, "asyncssh", mock_asyncssh_module)

    info = await collector._collect_via_ssh("192.168.1.92", "admin", "password")

    assert info is not None
    assert info["firmware_version"] == "OPNsense 24.7.1 (generic)"
    assert info["model"] == "generic"


@pytest.mark.asyncio
async def test_collect_via_ssh_connection_error(monkeypatch) -> None:
    """Test SSH collection handles connection errors gracefully."""
    collector = PfSenseCollector()

    def mock_connect_error(*args, **kwargs):
        raise Exception("Connection refused")

    mock_asyncssh_module = MagicMock()
    mock_asyncssh_module.PermissionDenied = MockPermissionDenied
    mock_asyncssh_module.HostKeyNotVerifiable = MockHostKeyNotVerifiable
    mock_asyncssh_module.connect = mock_connect_error

    monkeypatch.setitem(sys.modules, "asyncssh", mock_asyncssh_module)

    with pytest.raises(ConnectionError, match="SSH connection failed"):
        await collector._collect_via_ssh("192.168.1.92", "admin", "wrongpassword")


@pytest.mark.asyncio
async def test_collect_via_snmp_success(monkeypatch) -> None:
    """Test SNMP collection with mocked pysnmp."""
    import pysnmp.hlapi.asyncio as hlapi

    collector = PfSenseCollector()

    # Create a mock value that can be converted to string and int.
    class MockValue:
        def __init__(self, value: str):
            self.value = value

        def __str__(self) -> str:
            return self.value

        def __int__(self) -> int:
            return 12345

    # Track OIDs and create mock identity/type objects.
    class MockIdentity:
        def __init__(self, oid: str):
            self.oid = oid

    class MockObjectType:
        def __init__(self, identity: MockIdentity):
            self.identity = identity
            # Store in private attribute for retrieval
            self._ObjectType__args = (identity,)

    async def mock_get_cmd(engine, auth, transport, context, *var_binds):
        if var_binds:
            obj_type = var_binds[0]
            oid_str = obj_type.identity.oid

            if oid_str == "1.3.6.1.2.1.1.1.0":  # sysDescr
                return (None, 0, 0, [(oid_str, MockValue("pfSense 2.7.0-RELEASE (SG-5100)"))])
            elif oid_str == "1.3.6.1.2.1.1.3.0":  # sysUptime
                return (None, 0, 0, [(oid_str, MockValue("12345"))])
        return (None, 0, 0, [])

    # Mock ObjectIdentity as a function that returns MockIdentity.
    def mock_object_identity(oid: str):
        return MockIdentity(oid)

    # Mock ObjectType as a function that returns MockObjectType.
    def mock_object_type(identity):
        return MockObjectType(identity)

    monkeypatch.setattr(hlapi, "get_cmd", mock_get_cmd)
    monkeypatch.setattr(hlapi, "SnmpEngine", MagicMock)
    monkeypatch.setattr(hlapi, "CommunityData", MagicMock)
    monkeypatch.setattr(hlapi, "ContextData", MagicMock)
    monkeypatch.setattr(hlapi, "ObjectType", mock_object_type)
    monkeypatch.setattr(hlapi, "ObjectIdentity", mock_object_identity)

    # Mock UdpTransportTarget.create as an async function.
    async def mock_create(*args, **kwargs):
        return MagicMock()

    monkeypatch.setattr(hlapi, "UdpTransportTarget", MagicMock(create=mock_create))

    info = await collector._collect_via_snmp("192.168.1.92", "public")

    assert info is not None
    assert info["sys_descr"] == "pfSense 2.7.0-RELEASE (SG-5100)"
    assert info["model"] == "SG-5100"
    assert info["firmware_version"] == "pfSense 2.7.0-RELEASE"
    assert info["state"] == "up"
    assert info["uptime"] == 12345


@pytest.mark.asyncio
async def test_collect_via_snmp_error_indication(monkeypatch) -> None:
    """Test SNMP collection handles error indications."""
    import pysnmp.hlapi.asyncio as hlapi

    collector = PfSenseCollector()

    async def mock_get_cmd_error(engine, auth, transport, context, *var_binds):
        return ("Host not reachable", 1, 0, [])

    # Create mock identity/type objects.
    class MockIdentity:
        def __init__(self, oid: str):
            self.oid = oid

    class MockObjectType:
        def __init__(self, identity: MockIdentity):
            self.identity = identity

    def mock_object_identity(oid: str):
        return MockIdentity(oid)

    def mock_object_type(identity):
        return MockObjectType(identity)

    monkeypatch.setattr(hlapi, "get_cmd", mock_get_cmd_error)
    monkeypatch.setattr(hlapi, "SnmpEngine", MagicMock)
    monkeypatch.setattr(hlapi, "CommunityData", MagicMock)
    monkeypatch.setattr(hlapi, "ContextData", MagicMock)
    monkeypatch.setattr(hlapi, "ObjectType", mock_object_type)
    monkeypatch.setattr(hlapi, "ObjectIdentity", mock_object_identity)

    async def mock_create(*args, **kwargs):
        return MagicMock()

    monkeypatch.setattr(hlapi, "UdpTransportTarget", MagicMock(create=mock_create))

    with pytest.raises(RuntimeError, match="SNMP query failed"):
        await collector._collect_via_snmp("192.168.1.92", "public")


@pytest.mark.asyncio
async def test_collect_happy_path(monkeypatch) -> None:
    """Test the full collect() orchestration: SSH + SNMP together.

    Exercises the public collect() method end-to-end with both SSH and SNMP
    returning valid data. Verifies that fields merge correctly and a DiscoveredDevice
    is built with hostname, model, manufacturer, role, and management info.
    """
    import pysnmp.hlapi.asyncio as hlapi

    collector = PfSenseCollector()

    # Load fixture data for SSH responses.
    with open(FIXTURES_DIR / "ssh_show_version_sg5100.txt") as f:
        version_output = f.read()
    with open(FIXTURES_DIR / "ssh_ifconfig_output.txt") as f:
        ifconfig_output = f.read()

    # Set up SSH mock.
    mock_conn = MagicMock()

    async def mock_run(cmd, **kwargs):
        result = MagicMock()
        if cmd == "opnsense-version":
            raise Exception("opnsense-version not available")
        elif cmd == "show version":
            result.stdout = version_output
        elif cmd == "cat /etc/version":
            raise Exception("File not found")
        elif cmd == "cat /etc/os-release":
            raise Exception("File not found")
        elif cmd == "cat /etc/platform":
            result.stdout = "pfSense"
        elif cmd == "hostname":
            result.stdout = "pfSense.local"
        elif cmd == "ifconfig":
            result.stdout = ifconfig_output
        else:
            raise Exception(f"Unexpected command: {cmd}")
        return result

    mock_conn.run = mock_run

    def mock_connect(*args, **kwargs):
        return AsyncContextManager(mock_conn)

    mock_asyncssh_module = MagicMock()
    mock_asyncssh_module.PermissionDenied = MockPermissionDenied
    mock_asyncssh_module.HostKeyNotVerifiable = MockHostKeyNotVerifiable
    mock_asyncssh_module.connect = mock_connect

    monkeypatch.setitem(sys.modules, "asyncssh", mock_asyncssh_module)

    # Set up SNMP mock.
    class MockValue:
        def __init__(self, value: str):
            self.value = value

        def __str__(self) -> str:
            return self.value

        def __int__(self) -> int:
            return 123456789

    class MockIdentity:
        def __init__(self, oid: str):
            self.oid = oid

    class MockObjectType:
        def __init__(self, identity: MockIdentity):
            self.identity = identity

    async def mock_get_cmd(engine, auth, transport, context, *var_binds):
        if var_binds:
            obj_type = var_binds[0]
            oid_str = obj_type.identity.oid

            if oid_str == "1.3.6.1.2.1.1.1.0":  # sysDescr
                return (None, 0, 0, [(oid_str, MockValue("pfSense 2.7.0-RELEASE (SG-5100)"))])
            elif oid_str == "1.3.6.1.2.1.1.3.0":  # sysUptime
                return (None, 0, 0, [(oid_str, MockValue("123456789"))])
        return (None, 0, 0, [])

    def mock_object_identity(oid: str):
        return MockIdentity(oid)

    def mock_object_type(identity):
        return MockObjectType(identity)

    monkeypatch.setattr(hlapi, "get_cmd", mock_get_cmd)
    monkeypatch.setattr(hlapi, "SnmpEngine", MagicMock)
    monkeypatch.setattr(hlapi, "CommunityData", MagicMock)
    monkeypatch.setattr(hlapi, "ContextData", MagicMock)
    monkeypatch.setattr(hlapi, "ObjectType", mock_object_type)
    monkeypatch.setattr(hlapi, "ObjectIdentity", mock_object_identity)

    async def mock_create(*args, **kwargs):
        return MagicMock()

    monkeypatch.setattr(hlapi, "UdpTransportTarget", MagicMock(create=mock_create))

    # Set up environment variables for collect().
    env = {
        "PFSENSE_HOST": "192.168.1.93",
        "PFSENSE_USERNAME": "admin",
        "PFSENSE_PASSWORD": "pfsense",
        "PFSENSE_USE_SNMP": "true",
        "PFSENSE_SNMP_COMMUNITY": "public",
    }

    with patch.dict(os.environ, env, clear=False):
        result = await collector.collect()

    # Verify the result structure.
    assert result.collector == "pfsense"
    assert len(result.devices) == 1
    assert result.notes == []

    device = result.devices[0]
    # SSH name takes priority over host.
    assert device.name == "pfSense.local"
    # Model extracted from SSH version string.
    assert device.model == "SG-5100"
    # Manufacturer is constant.
    assert device.manufacturer == "Netgate"
    # Role derived from model.
    assert device.role == "gateway"
    # Primary IP from SSH ifconfig.
    assert device.primary_ip == "192.168.1.1"
    # Management status "active" comes from state "up" (SNMP uptime > 0).
    assert device.management is not None
    assert device.management.status == "active"
    # Firmware version from SSH.
    assert device.management.firmware == "pfSense 2.7.0-RELEASE (SG-5100)"
