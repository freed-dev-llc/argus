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
from .models import (
    manufacturer_from_version,
    normalize_model,
    role_from_model,
    status_from_state,
)

#: Environment variables this pack consumes. Canonical prefix is ``FIREWALL_``; the legacy
#: ``PFSENSE_`` prefix is still honored as a backward-compatible alias (see ``_read_targets``).
CONFIG_VARS = (
    "FIREWALL_HOST",
    "FIREWALL_USERNAME",
    "FIREWALL_PASSWORD",
    # Optional:
    # - FIREWALL_SITE: NetBox site the firewall is enrolled into (default "Default")
    # - FIREWALL_USE_SNMP: "true" to enable SNMP (requires pysnmp)
    # - FIREWALL_SNMP_COMMUNITY: SNMP v2c community (default "public")
    # Additional firewalls: append a numeric suffix — FIREWALL_HOST_2 / FIREWALL_USERNAME_2 /
    # FIREWALL_PASSWORD_2 / FIREWALL_SITE_2 (etc.) for a second target, _3 for a third, ...
    # Legacy alias: every FIREWALL_* var may instead be given as PFSENSE_* (canonical wins).
)

#: Highest numbered firewall target the collector scans for (FIREWALL_HOST .. FIREWALL_HOST_16).
_MAX_TARGETS = 16


def _target_env(base: str, suffix: str) -> str:
    """Read one target var, preferring the canonical ``FIREWALL_`` prefix over legacy ``PFSENSE_``."""
    return os.environ.get(f"FIREWALL_{base}{suffix}") or os.environ.get(f"PFSENSE_{base}{suffix}", "")


def _read_targets() -> list[dict[str, Any]]:
    """Read one or more firewall targets from the environment.

    Target 1 uses the unsuffixed vars (``FIREWALL_HOST`` / ``FIREWALL_USERNAME`` / ...); targets
    2..N use a ``_<n>`` suffix (``FIREWALL_HOST_2``, ...). Any index whose host is set becomes a
    target, so gaps are tolerated. Each var also accepts the legacy ``PFSENSE_`` prefix as an
    alias. Backward compatible: a lone ``FIREWALL_HOST`` (or ``PFSENSE_HOST``) yields one target.
    """
    targets: list[dict[str, Any]] = []
    for i in range(1, _MAX_TARGETS + 1):
        suffix = "" if i == 1 else f"_{i}"
        host = _target_env("HOST", suffix).strip()
        if not host:
            continue
        targets.append(
            {
                "label": f"#{i}",
                "host": host,
                "username": _target_env("USERNAME", suffix).strip(),
                "password": _target_env("PASSWORD", suffix).strip(),
                "site": _target_env("SITE", suffix).strip() or "Default",
                "use_snmp": _target_env("USE_SNMP", suffix).lower() in ("true", "1", "yes"),
                "community": _target_env("SNMP_COMMUNITY", suffix).strip() or "public",
            }
        )
    return targets


class FirewallCollector(Collector):
    """Discover pfSense/OPNsense firewalls and their network state via SSH and SNMP."""

    name = "firewall"

    async def collect(self) -> DiscoveryResult:
        result = DiscoveryResult(collector=self.name)

        targets = _read_targets()
        if not targets:
            result.notes.append(
                "firewall pack not configured: set FIREWALL_HOST / FIREWALL_USERNAME / "
                "FIREWALL_PASSWORD (append _2, _3, ... for additional firewalls)."
            )
            return result

        for target in targets:
            await self._collect_target(target, result)

        if not result.devices:
            result.notes.append(
                "firewall collector: no devices discovered "
                "(SSH/SNMP access may be limited or unconfigured)."
            )

        return result

    async def _collect_target(self, target: dict[str, Any], result: DiscoveryResult) -> None:
        """Discover one firewall target, appending its device / IPs / notes to ``result``.

        A per-target failure (missing creds, SSH error) is recorded as a note and never aborts
        the other targets — partial discovery beats none (ADR-0003).
        """
        host = target["host"]
        label = target["label"]

        # A configured host with no creds is a misconfiguration: note it and skip this target.
        if not (target["username"] and target["password"]):
            result.notes.append(
                f"firewall target {label} ({host}) missing username/password; skipped."
            )
            return

        # Resolve credentials from env vars or file paths.
        try:
            host, username, password = load_ssh_creds(
                host, target["username"], target["password"]
            )
        except FileNotFoundError as exc:
            result.notes.append(f"firewall target {label} credential file not found: {exc}")
            return
        except Exception as exc:
            result.notes.append(f"firewall target {label} credential loading failed: {exc}")
            return

        # --- SSH collection (primary) ---
        try:
            system_info = await self._collect_via_ssh(host, username, password)
        except Exception as exc:
            result.notes.append(f"SSH collection failed for {label} ({host}): {exc}")
            system_info = None

        # --- SNMP collection (secondary, if enabled) ---
        snmp_info = None
        if target["use_snmp"]:
            try:
                community = load_snmp_creds(target["community"])
                snmp_info = await self._collect_via_snmp(host, community)
            except Exception as exc:
                result.notes.append(f"SNMP collection failed for {label} ({host}): {exc}")

        # --- Synthesize discovered device (SSH takes priority over SNMP) ---
        combined_info: dict[str, Any] = {}
        if snmp_info:
            combined_info.update(snmp_info)
        if system_info:
            combined_info.update(system_info)

        if not combined_info:
            return

        mgmt = DeviceManagement(
            status=status_from_state(combined_info.get("state")),
            firmware=combined_info.get("firmware_version"),
            mgmt_ip=combined_info.get("primary_ip"),
        )
        # Infer role from model, falling back to the firmware/version string.
        inferred_role = role_from_model(combined_info.get("model"))
        if not inferred_role and combined_info.get("firmware_version"):
            inferred_role = role_from_model(combined_info.get("firmware_version"))

        result.devices.append(
            DiscoveredDevice(
                name=combined_info.get("hostname") or host,
                primary_ip=combined_info.get("primary_ip"),
                site=target["site"],
                # OPNsense → Deciso, pfSense/Netgate → Netgate, detected from the version string.
                manufacturer=manufacturer_from_version(
                    combined_info.get("firmware_version") or combined_info.get("model")
                ),
                # Arch tokens (amd64, ...) from a generic install become "Virtual Machine".
                model=normalize_model(combined_info.get("model")),
                role=inferred_role,
                management=mgmt if any((mgmt.status, mgmt.firmware, mgmt.mgmt_ip)) else None,
                raw=combined_info,
            )
        )
        if combined_info.get("primary_ip"):
            result.ip_addresses.append(combined_info["primary_ip"])

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

