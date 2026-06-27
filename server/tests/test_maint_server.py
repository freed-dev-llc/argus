"""The maintenance MCP surface is separate from the product `argus` server (ADR-0012).

These assert the two FastMCP servers carry disjoint tool sets, so the read/preview-only
maintenance tools never leak into the product network-automation surface (and vice versa).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from argus import maint_server, server

_MAINT_TOOLS = {"release_current", "release_verify", "release_bump"}


async def _tool_names(mcp: FastMCP) -> set[str]:
    return {tool.name for tool in await mcp.list_tools()}


async def test_servers_are_named_separately() -> None:
    assert maint_server.mcp.name == "argus-maint"
    assert server.mcp.name == "argus"


async def test_maint_server_exposes_the_release_tools() -> None:
    assert await _tool_names(maint_server.mcp) == _MAINT_TOOLS


async def test_product_server_excludes_maintenance_tools() -> None:
    product = await _tool_names(server.mcp)
    assert product.isdisjoint(_MAINT_TOOLS)
    # …and still carries its network-automation tools, unchanged.
    assert {"health", "list_devices", "drift_report", "reconcile_apply"} <= product
