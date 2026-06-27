"""FastMCP server exposing Argus maintenance/devtools over stdio.

A *separate* surface from the product ``argus`` network-automation server (``server.py``):
this one wraps the repo-maintenance devtools (the ``argus-release`` engine) for an MCP control
environment, so release/maintenance ops never appear alongside — and can't be confused with —
the NetBox tools agents call against a live network. See ADR-0012.

First cut is read/preview-only: current version, build verify, and a dry-run bump preview.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .devtools.maint_tools import release_bump, release_current, release_verify

mcp = FastMCP("argus-maint")

# Maintenance / devtools (read + preview only — nothing here writes; see ADR-0012)
mcp.tool()(release_current)
mcp.tool()(release_verify)
mcp.tool()(release_bump)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
