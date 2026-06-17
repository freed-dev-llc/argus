"""Read-only NetBox tools — the agent-facing query surface."""

from __future__ import annotations

import asyncio
from typing import Any

from ..config import get_settings
from ..netbox.client import NetBoxClient

_client: NetBoxClient | None = None
_NOT_CONFIGURED = "NetBox not configured: set NETBOX_URL and NETBOX_TOKEN."


def _get_client() -> NetBoxClient:
    """Return a cached NetBox client, building it from settings on first use.

    Raises ``RuntimeError`` if NetBox is not configured.
    """
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.netbox_configured:
            raise RuntimeError(_NOT_CONFIGURED)
        _client = NetBoxClient(
            settings.netbox_url,
            settings.netbox_token,
            verify_ssl=settings.netbox_verify_ssl,
        )
    return _client


async def list_devices(site: str | None = None, role: str | None = None) -> dict[str, Any]:
    """List devices from NetBox (DCIM), optionally filtered by site and/or role slug."""
    try:
        client = _get_client()
    except RuntimeError as exc:
        return {"error": str(exc)}
    devices = await asyncio.to_thread(client.list_devices, site, role)
    return {"devices": devices, "count": len(devices)}


async def get_device(name: str) -> dict[str, Any]:
    """Get a single NetBox device by name."""
    try:
        client = _get_client()
    except RuntimeError as exc:
        return {"error": str(exc)}
    device = await asyncio.to_thread(client.get_device, name)
    if device is None:
        return {"error": f"Device '{name}' not found."}
    return {"device": device}


async def list_prefixes() -> dict[str, Any]:
    """List IPAM prefixes from NetBox."""
    try:
        client = _get_client()
    except RuntimeError as exc:
        return {"error": str(exc)}
    prefixes = await asyncio.to_thread(client.list_prefixes)
    return {"prefixes": prefixes, "count": len(prefixes)}


async def list_ip_addresses(prefix: str | None = None) -> dict[str, Any]:
    """List IPAM IP addresses, optionally scoped to a parent prefix (CIDR)."""
    try:
        client = _get_client()
    except RuntimeError as exc:
        return {"error": str(exc)}
    addresses = await asyncio.to_thread(client.list_ip_addresses, prefix)
    return {"ip_addresses": addresses, "count": len(addresses)}


async def search(query: str) -> dict[str, Any]:
    """Free-text search NetBox devices and IP addresses."""
    try:
        client = _get_client()
    except RuntimeError as exc:
        return {"error": str(exc)}
    return await asyncio.to_thread(client.search, query)
