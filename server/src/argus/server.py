"""FastMCP server exposing Argus tools over stdio (for coding agents)."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import __version__
from .config import get_settings
from .tools.discovery_tools import discovery_scan, list_collectors, network_topology
from .tools.practices_tools import evaluate_practices
from .tools.read_tools import (
    get_device,
    list_devices,
    list_ip_addresses,
    list_prefixes,
    search,
)
from .tools.reconcile_tools import drift_report, reconcile_apply

mcp = FastMCP("argus")


def _argus_version() -> str:
    """Installed distribution version; fall back to __version__ from a source tree."""
    try:
        return _pkg_version("argus-netbox")
    except PackageNotFoundError:  # not pip-installed (running from a bare checkout)
        return __version__


@mcp.tool()
async def health() -> dict[str, Any]:
    """Report Argus configuration and whether NetBox is reachable-by-config."""
    settings = get_settings()
    if not settings.netbox_configured:
        return {
            "status": "unconfigured",
            "detail": "set NETBOX_URL and NETBOX_TOKEN",
            "version": _argus_version(),
        }
    return {"status": "ok", "netbox_url": settings.netbox_url, "version": _argus_version()}


# Read tools (NetBox queries)
mcp.tool()(list_devices)
mcp.tool()(get_device)
mcp.tool()(list_prefixes)
mcp.tool()(list_ip_addresses)
mcp.tool()(search)

# Discovery tools (observe live network state)
mcp.tool()(list_collectors)
mcp.tool()(discovery_scan)
mcp.tool()(network_topology)

# Reconcile tools (review drift, apply changes — confirmation-gated)
mcp.tool()(drift_report)
mcp.tool()(reconcile_apply)

# Practices tools (advisory best-practice checks — read-only)
mcp.tool()(evaluate_practices)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
