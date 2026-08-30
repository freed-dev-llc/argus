"""Read-only discovery from the NetBird management REST API.

The collector deliberately requires a NetBird group and imports only peers in that
group. Overlay IPs are authoritative for off-LAN peers but must never replace LAN
management addresses on every mesh member (ADR-0017).
"""

from __future__ import annotations

from typing import Any

import httpx

from ....config import get_settings
from ...base import Collector, DeviceManagement, DiscoveredDevice, DiscoveryResult


def _items(payload: Any) -> list[dict[str, Any]]:
    """Accept NetBird's list response and common wrapped-list response shapes."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "results", "data", "peers", "groups"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _peer_ids(group: dict[str, Any]) -> set[str]:
    """Extract peer IDs from NetBird group payloads across API versions."""
    ids: set[str] = set()
    for peer in group.get("peers") or group.get("peer_ids") or []:
        value = peer.get("id") or peer.get("peer_id") if isinstance(peer, dict) else peer
        if value:
            ids.add(str(value))
    return ids


def _find_group(groups: list[dict[str, Any]], wanted: str) -> dict[str, Any] | None:
    key = wanted.strip().lower()
    for group in groups:
        if str(group.get("id") or "").lower() == key:
            return group
        if str(group.get("name") or "").strip().lower() == key:
            return group
    return None


def _name(peer: dict[str, Any]) -> str | None:
    value = peer.get("name") or peer.get("hostname") or peer.get("dns_label")
    if not value:
        return None
    # A peer name may be returned as an account-qualified FQDN. NetBox identity uses
    # the stable host label, matching the names emitted by the other collectors.
    return str(value).strip().split(".", 1)[0] or None


def _status(peer: dict[str, Any]) -> str | None:
    connected = peer.get("connected")
    if isinstance(connected, bool):
        return "active" if connected else "offline"
    return None


class NetBirdCollector(Collector):
    name = "netbird"
    ownership_tag = "argus-source-netbird"

    async def collect(self) -> DiscoveryResult:
        settings = get_settings()
        result = DiscoveryResult(
            collector=self.name,
            device_ownership_tag=self.ownership_tag,
        )
        if not settings.netbird_configured:
            result.notes.append(
                "NetBird not configured: set NETBIRD_URL, NETBIRD_API_TOKEN, "
                "and NETBIRD_GROUP."
            )
            return result

        base = settings.netbird_url.rstrip("/")
        headers = {
            "Authorization": f"Token {settings.netbird_api_token}",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                headers=headers,
                verify=settings.netbird_verify_ssl,
                timeout=settings.netbird_timeout,
            ) as client:
                group_response = await client.get(f"{base}/api/groups")
                group_response.raise_for_status()
                groups = _items(group_response.json())
                group = _find_group(groups, settings.netbird_group)
                if group is None:
                    result.notes.append(
                        f"NetBird group '{settings.netbird_group}' was not found; "
                        "no peers collected."
                    )
                    return result
                allowed = _peer_ids(group)
                if not allowed:
                    result.notes.append(
                        f"NetBird group '{settings.netbird_group}' contains no peers."
                    )
                    return result

                peer_response = await client.get(f"{base}/api/peers")
                peer_response.raise_for_status()
                peers = _items(peer_response.json())
        except (httpx.HTTPError, ValueError) as exc:
            result.notes.append(f"NetBird API request failed: {exc}")
            return result

        skipped_unnamed = 0
        for peer in peers:
            peer_id = str(peer.get("id") or peer.get("peer_id") or "")
            if peer_id not in allowed:
                continue
            name = _name(peer)
            if name is None:
                skipped_unnamed += 1
                continue
            ip = peer.get("ip") or peer.get("address")
            result.devices.append(
                DiscoveredDevice(
                    name=name,
                    primary_ip=str(ip) if ip else None,
                    site=settings.netbird_site or None,
                    role=settings.netbird_role or None,
                    model=settings.netbird_model or None,
                    manufacturer=(
                        settings.netbird_manufacturer
                        if settings.netbird_model and settings.netbird_manufacturer
                        else None
                    ),
                    management=DeviceManagement(
                        status=_status(peer),
                        firmware=str(peer.get("version") or peer.get("agent_version") or "")
                        or None,
                        mgmt_ip=str(ip) if ip else None,
                        mgmt_interface="wt0" if ip else None,
                    ),
                    raw=peer,
                )
            )
            if ip:
                result.ip_addresses.append(str(ip))

        result.notes.append(
            f"Discovered {len(result.devices)} peer(s) in NetBird group "
            f"'{settings.netbird_group}'."
        )
        if skipped_unnamed:
            result.notes.append(f"Skipped {skipped_unnamed} NetBird peer(s) without a name.")
        return result
