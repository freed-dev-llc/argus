"""UniFi discovery collector.

Pulls devices from the UniFi Network **Integration API** (X-API-KEY auth, read-only),
mirroring the approach in the sibling ``aria-unifi-mcp`` server, and normalizes them into
a :class:`DiscoveryResult`. Requires ``UNIFI_URL`` + ``UNIFI_API_TOKEN`` (see config).

Endpoints used (base ``{UNIFI_URL}/proxy/network/integration/v1``):
- ``GET /sites`` → ``{"data": [{id, internalReference, name}]}``
- ``GET /sites/{site_id}/devices`` → ``{"data": [{name, mac, model, state, ipAddress, ...}]}``
"""

from __future__ import annotations

from typing import Any

import httpx

from ...config import get_settings
from ..base import (
    Collector,
    DiscoveredClient,
    DiscoveredDevice,
    DiscoveredLink,
    DiscoveryResult,
)

# Best-effort NetBox device-role inference from the UniFi model string. The Integration
# API returns full model names ("UniFi Dream Machine PRO SE", "USW Pro 48 PoE", "U6 Pro"),
# so match on keywords rather than code prefixes. Order matters — gateway is checked first.
_ROLE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gateway", ("dream machine", "udm", "uxg", "ucg", "ugw", "cloud gateway", "security gateway", "gateway")),
    ("switch", ("usw", "switch", "aggregation", "us-")),
    ("ap", ("u6", "u7", "uap", "access point", "nanohd", "ac lite", "ac pro", "ac mesh")),
)


def _role_from_model(model: str | None) -> str | None:
    if not model:
        return None
    text = model.lower()
    for role, keywords in _ROLE_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return role
    return None


def _pick_site(sites: list[dict[str, Any]], reference: str) -> dict[str, Any] | None:
    for site in sites:
        if site.get("internalReference") == reference:
            return site
    return sites[0] if sites else None


async def _get(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    response = await client.get(url)
    response.raise_for_status()
    data: dict[str, Any] = response.json()
    return data


class UniFiCollector(Collector):
    name = "unifi"

    async def collect(self) -> DiscoveryResult:
        settings = get_settings()
        result = DiscoveryResult(collector=self.name)

        if not settings.unifi_configured:
            result.notes.append("UniFi not configured: set UNIFI_URL and UNIFI_API_TOKEN.")
            return result

        base = settings.unifi_url.rstrip("/") + "/proxy/network/integration/v1"
        headers = {"X-API-KEY": settings.unifi_api_token, "Accept": "application/json"}

        try:
            async with httpx.AsyncClient(
                headers=headers, verify=settings.unifi_verify_ssl, timeout=30.0
            ) as client:
                sites = (await _get(client, f"{base}/sites")).get("data", [])
                site = _pick_site(sites, settings.unifi_site)
                if site is None:
                    result.notes.append("No UniFi sites returned by the controller.")
                    return result
                devices = (await _get(client, f"{base}/sites/{site['id']}/devices")).get(
                    "data", []
                )
                # Clients are best-effort: a controller without the endpoint still yields devices.
                try:
                    clients = (
                        await _get(client, f"{base}/sites/{site['id']}/clients?limit=200")
                    ).get("data", [])
                except httpx.HTTPError as exc:
                    clients = []
                    result.notes.append(f"UniFi clients endpoint unavailable: {exc}")
                # Topology (best-effort): each device's detail carries its uplink device id.
                uplinks: dict[str, str] = {}
                for device in devices:
                    did = device.get("id")
                    if not did:
                        continue
                    try:
                        detail = await _get(client, f"{base}/sites/{site['id']}/devices/{did}")
                    except httpx.HTTPError:
                        continue
                    remote = (detail.get("uplink") or {}).get("deviceId")
                    if remote:
                        uplinks[did] = remote
        except httpx.HTTPError as exc:
            result.notes.append(f"UniFi API request failed: {exc}")
            return result

        site_name = site.get("name") or site.get("internalReference")
        for device in devices:
            ip = device.get("ipAddress") or device.get("ip")
            result.devices.append(
                DiscoveredDevice(
                    name=device.get("name") or device.get("mac") or "unknown",
                    mac=device.get("mac"),
                    primary_ip=ip,
                    site=site_name,
                    role=_role_from_model(device.get("model")),
                    model=device.get("model"),
                    manufacturer="Ubiquiti",
                    raw=device,
                )
            )
            if ip:
                result.ip_addresses.append(ip)

        for entry in clients:
            ip = entry.get("ipAddress") or entry.get("ip")
            result.clients.append(
                DiscoveredClient(
                    mac=entry.get("macAddress") or entry.get("mac"),
                    ip=ip,
                    hostname=entry.get("name") or entry.get("hostname"),
                    raw=entry,
                )
            )
            if ip:
                result.ip_addresses.append(ip)

        id_to_name = {
            d.get("id"): (d.get("name") or d.get("macAddress") or d.get("id"))
            for d in devices
            if d.get("id")
        }
        for local_id, remote_id in uplinks.items():
            local = id_to_name.get(local_id)
            remote = id_to_name.get(remote_id)
            if local and remote:
                result.links.append(DiscoveredLink(local_device=local, remote_device=remote))

        result.notes.append(
            f"Discovered {len(result.devices)} device(s), {len(result.clients)} client(s), "
            f"{len(result.links)} link(s) from UniFi site '{site_name}'."
        )
        return result
