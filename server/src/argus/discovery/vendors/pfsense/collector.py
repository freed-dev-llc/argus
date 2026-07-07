"""pfSense/OPNsense discovery collector.

Discovers network devices and gathers system information from pfSense/OPNsense firewalls
via SSH CLI (primary) and SNMP (secondary). Normalizes findings into a DiscoveryResult.

SSH endpoints queried (via standard OpenSSH):
- ``show version`` (or ``cat /etc/version``) → system info, firmware
- ``ifconfig`` / ``netstat`` → interfaces, routing, management IPs
- Captured state files → config backup, device inventory (if available)

SNMP endpoints (v2c, v3 via pysnmp if available):
- ``sysDescr``, ``sysUptime`` → system health, uptime
- ``ifTable`` → interfaces (count, state, MAC addresses)

Both are read-only and honor the SPI's degrade-gracefully contract: partial discovery
is better than no discovery (ADR-0003).
"""

from __future__ import annotations

import ipaddress
import os
import re
from typing import Any

from ...base import Collector, DeviceManagement, DiscoveredDevice, DiscoveryResult
from .credentials import load_snmp_creds, load_ssh_creds
from .models import MANUFACTURER, role_from_model, status_from_state

#: Environment variables this pack consumes.
CONFIG_VARS = (
    "PFSENSE_HOST",
    "PFSENSE_USERNAME",
    "PFSENSE_PASSWORD",
    # Optional:
    # - PFSENSE_USE_SNMP: "true" to enable SNMP (requires pysnmp)
    # - PFSENSE_SNMP_COMMUNITY: SNMP v2c community (default "public")
)


class PfSenseCollector(Collector):
    """Discover pfSense/OPNsense firewalls and their network state via SSH and SNMP."""

    name = "pfsense"

    async def collect(self) -> DiscoveryResult:
        result = DiscoveryResult(collector=self.name)

        # Check if configuration is present.
        host = os.environ.get("PFSENSE_HOST", "").strip()
        username = os.environ.get("PFSENSE_USERNAME", "").strip()
        password = os.environ.get("PFSENSE_PASSWORD", "").strip()

        if not all((host, username, password)):
            missing = []
            if not host:
                missing.append("PFSENSE_HOST")
            if not username:
                missing.append("PFSENSE_USERNAME")
            if not password:
                missing.append("PFSENSE_PASSWORD")
            result.notes.append(f"pfsense pack not configured: set {', '.join(missing)}.")
            return result

        # Resolve credentials from env vars or file paths.
        try:
            host, username, password = load_ssh_creds(host, username, password)
        except FileNotFoundError as exc:
            result.notes.append(f"pfsense credential file not found: {exc}")
            return result
        except Exception as exc:
            result.notes.append(f"pfsense credential loading failed: {exc}")
            return result

        # --- SSH collection (primary) ---
        try:
            system_info = await self._collect_via_ssh(host, username, password)
        except Exception as exc:
            result.notes.append(f"SSH collection failed: {exc}")
            system_info = None

        # --- SNMP collection (secondary, if enabled) ---
        snmp_info = None
        use_snmp = os.environ.get("PFSENSE_USE_SNMP", "").lower() in ("true", "1", "yes")
        if use_snmp:
            try:
                community = os.environ.get("PFSENSE_SNMP_COMMUNITY", "public").strip()
                community = load_snmp_creds(community)
                snmp_info = await self._collect_via_snmp(host, community)
            except Exception as exc:
                result.notes.append(f"SNMP collection failed: {exc}")

        # --- Synthesize discovered device ---
        # Merge SSH and SNMP results (SSH takes priority).
        combined_info = {}
        if snmp_info:
            combined_info.update(snmp_info)
        if system_info:
            combined_info.update(system_info)

        if combined_info:
            mgmt = DeviceManagement(
                status=status_from_state(combined_info.get("state")),
                firmware=combined_info.get("firmware_version"),
                mgmt_ip=combined_info.get("primary_ip"),
            )
            # Infer role from model or firmware version
            inferred_role = role_from_model(combined_info.get("model"))
            if not inferred_role and combined_info.get("firmware_version"):
                # Fallback: check firmware version for product keywords
                inferred_role = role_from_model(combined_info.get("firmware_version"))

            result.devices.append(
                DiscoveredDevice(
                    name=combined_info.get("hostname") or host,
                    primary_ip=combined_info.get("primary_ip"),
                    manufacturer=MANUFACTURER,
                    model=combined_info.get("model"),
                    role=inferred_role,
                    management=mgmt if any((mgmt.status, mgmt.firmware, mgmt.mgmt_ip)) else None,
                    raw=combined_info,
                )
            )
            if combined_info.get("primary_ip"):
                result.ip_addresses.append(combined_info["primary_ip"])

        if not result.devices:
            result.notes.append(
                "pfsense collector: no devices discovered "
                "(SSH/SNMP access may be limited or unconfigured)."
            )

        return result

    async def _collect_via_ssh(
        self, host: str, username: str, password: str
    ) -> dict[str, Any] | None:
        """Collect system info via SSH CLI (read-only commands).

        Queries:
        - 'show version' (or fallback 'cat /etc/version') → hostname, model, firmware
        - 'ifconfig' → primary LAN IP (non-loopback, non-link-local, private)

        Returns dict with keys: hostname, model, firmware_version, primary_ip
        or None if all queries fail.
        """
        try:
            import asyncssh
        except ImportError as exc:
            raise ImportError("asyncssh not installed; install with: pip install 'argus[discovery]'") from exc

        info: dict[str, Any] = {}

        try:
            async with asyncssh.connect(
                host, username=username, password=password, known_hosts=None
            ) as conn:
                # For pfSense/OPNsense: try selecting shell option if menu appears
                try:
                    async with await conn.open_session(term_type='xterm') as process:
                        # Send "8" to select shell option (pfSense menu)
                        process.stdin.write(b"8\n")
                        await process.stdin.drain()
                        # Give the shell a moment to initialize
                        import asyncio
                        await asyncio.sleep(0.2)
                except Exception:
                    pass  # Might not be interactive, fall through to direct commands

                # Query version info - try multiple approaches
                version_output = None

                # Try 1: OPNsense-specific command
                try:
                    result = await conn.run("opnsense-version")
                    if result.stdout:
                        version_output = result.stdout
                except Exception:
                    pass

                # Try 2: pfSense-specific "show version" command
                if not version_output:
                    try:
                        result = await conn.run("show version", input="8\n")
                        if result.stdout:
                            version_output = result.stdout
                    except Exception:
                        pass

                # Try 3: cat /etc/version (pfSense file)
                if not version_output:
                    try:
                        result = await conn.run("cat /etc/version")
                        if result.stdout:
                            version_output = result.stdout
                    except Exception:
                        pass

                # Try 4: Extract from /etc/os-release or uname
                if not version_output:
                    try:
                        result = await conn.run("cat /etc/os-release")
                        if result.stdout:
                            version_output = result.stdout
                    except Exception:
                        pass

                if version_output:
                    # asyncssh can return bytes or str; normalize to str
                    if isinstance(version_output, bytes):
                        version_output = version_output.decode("utf-8")
                    version_output = version_output.strip()
                    # Parse version string: "pfSense 2.8.1-RELEASE (SG-5100)" or "OPNsense 26.1.11_6 (amd64)"
                    info["firmware_version"] = version_output
                    # Extract model/architecture from parentheses if present
                    match = re.search(r"\(([^)]+)\)", version_output)
                    if match:
                        model_str = match.group(1)
                        info["model"] = model_str

                # Try to get product/platform info (pfSense-specific)
                try:
                    result = await conn.run("cat /etc/platform")
                    if result.stdout:
                        platform = result.stdout.strip()
                        if isinstance(platform, bytes):
                            platform = platform.decode("utf-8").strip()
                        if not info.get("model"):
                            info["model"] = platform
                except Exception:
                    pass

                # Query hostname.
                try:
                    result = await conn.run("hostname")
                    hostname = result.stdout
                    if hostname:
                        if isinstance(hostname, bytes):
                            hostname = hostname.decode("utf-8")
                        hostname = hostname.strip()
                        if hostname:
                            info["hostname"] = hostname
                except Exception:
                    pass

                # Query interfaces to find primary IP.
                try:
                    result = await conn.run("ifconfig")
                    ifconfig_output = result.stdout
                    if ifconfig_output:
                        # asyncssh can return bytes or str; normalize to str
                        if isinstance(ifconfig_output, bytes):
                            ifconfig_output = ifconfig_output.decode("utf-8")
                        primary_ip = self._extract_primary_ip(ifconfig_output)
                        if primary_ip:
                            info["primary_ip"] = primary_ip
                except Exception:
                    pass

        except asyncssh.PermissionDenied as exc:
            raise PermissionError(f"SSH authentication failed: {exc}") from exc
        except asyncssh.HostKeyNotVerifiable as exc:
            raise ConnectionError(f"SSH host key verification failed: {exc}") from exc
        except Exception as exc:
            raise ConnectionError(f"SSH connection failed: {exc}") from exc

        return info if info else None

    @staticmethod
    def _extract_primary_ip(ifconfig_output: str) -> str | None:
        """Extract the primary LAN IP from ifconfig output.

        Looks for the first non-loopback, non-link-local private IP address.
        Common interface names: em0, em1, igb0, igb1, etc.
        """
        lines = ifconfig_output.split("\n")
        current_interface = None

        for line in lines:
            # Interface lines typically start with a name (em0, em1, etc.)
            if line and not line[0].isspace():
                current_interface = line.split(":")[0].strip()
            # Look for "inet " (IPv4) lines within interfaces.
            elif "inet " in line and current_interface:
                # Extract IP address from "inet 192.168.1.100 netmask 0xffffff00"
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0] == "inet":
                    ip_str = parts[1]
                    try:
                        addr = ipaddress.ip_address(ip_str)
                        # Skip loopback and link-local; accept private addresses.
                        if (
                            not addr.is_loopback
                            and not addr.is_link_local
                            and addr.is_private
                        ):
                            return ip_str
                    except ValueError:
                        continue

        return None

    async def _collect_via_snmp(self, host: str, community: str) -> dict[str, Any]:
        """Collect system info via SNMP v2c (read-only).

        Requires pysnmp (declared in optional discovery dependencies). Queries:
        - sysDescr (1.3.6.1.2.1.1.1.0) → system description (e.g., "pfSense 2.7.0 SG-5100")
        - sysUptime (1.3.6.1.2.1.1.3.0) → uptime (hundredths of seconds)

        Uses the pysnmp 7.x async API (pysnmp.hlapi.asyncio).
        """
        try:
            import pysnmp.hlapi.asyncio as hlapi
        except ImportError as exc:
            raise ImportError("pysnmp not installed; install with: pip install 'argus[discovery]'") from exc

        info: dict[str, Any] = {}
        engine = hlapi.SnmpEngine()
        transport = await hlapi.UdpTransportTarget.create(
            (host, 161), timeout=5, retries=2
        )
        auth = hlapi.CommunityData(community, mpModel=1)  # v2c

        try:
            # Query sysDescr.
            error_indication, error_status, error_index, var_binds = await hlapi.get_cmd(
                engine,
                auth,
                transport,
                hlapi.ContextData(),
                hlapi.ObjectType(hlapi.ObjectIdentity("1.3.6.1.2.1.1.1.0")),
            )

            if error_indication:
                raise RuntimeError(f"SNMP query failed: {error_indication}")

            for _obj_name, obj_val in var_binds:
                if obj_val is not None:
                    sys_descr = str(obj_val)
                    info["sys_descr"] = sys_descr
                    # Try to extract model and firmware from sysDescr.
                    # Example: "pfSense 2.7.0-RELEASE (SG-5100)"
                    match = re.search(r"\(([^)]+)\)", sys_descr)
                    if match:
                        info["model"] = match.group(1)
                    # Extract firmware/version.
                    parts = sys_descr.split()
                    if len(parts) >= 2:
                        info["firmware_version"] = " ".join(parts[:2])

            # Query sysUptime (optional, for state tracking).
            error_indication, error_status, error_index, var_binds = await hlapi.get_cmd(
                engine,
                auth,
                transport,
                hlapi.ContextData(),
                hlapi.ObjectType(hlapi.ObjectIdentity("1.3.6.1.2.1.1.3.0")),
            )
            if error_indication:
                pass  # Best effort
            else:
                for _obj_name, obj_val in var_binds:
                    if obj_val is not None:
                        info["uptime"] = int(obj_val)
                        # Device is "up" if uptime is > 0.
                        if int(obj_val) > 0:
                            info["state"] = "up"

        except Exception as exc:
            raise RuntimeError(f"SNMP collection failed: {exc}") from exc

        return info if info else {}

