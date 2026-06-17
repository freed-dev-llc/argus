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
from ..base import Collector, DiscoveredDevice, DiscoveryResult

# Coarse NetBox device-role inference from the UniFi model prefix. Best-effort only;
# the reconcile engine (P2) is responsible for final role assignment.
_MODEL_ROLE_PREFIXES: dict[str, str] = {
    "UAP": "ap",
    "U6": "ap",
    "U7": "ap",
    "USW": "switch",
    "US-": "switch",
    "UDM": "gateway",
    "UGW": "gateway",
    "UXG": "gateway",
    "UCG": "gateway",
}


def _role_from_model(model: str | None) -> str | None:
    if not model:
        return None
    upper = model.upper()
    for prefix, role in _MODEL_ROLE_PREFIXES.items():
        if upper.startswith(prefix):
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

        result.notes.append(
            f"Discovered {len(result.devices)} device(s) from UniFi site '{site_name}'."
        )
        return result
