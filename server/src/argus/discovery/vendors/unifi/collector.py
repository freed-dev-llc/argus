"""UniFi discovery collector.

Pulls devices from the UniFi Network **Integration API** (X-API-KEY auth, read-only),
mirroring the approach in the sibling ``aria-unifi-mcp`` server, and normalizes them into
a :class:`DiscoveryResult`. Requires ``UNIFI_URL`` + ``UNIFI_API_TOKEN`` (see config).

Endpoints used (base ``{UNIFI_URL}/proxy/network/integration/v1``):
- ``GET /sites`` → ``{"data": [{id, internalReference, name}]}``
- ``GET /sites/{site_id}/devices`` → ``{"data": [{name, mac, model, state, ipAddress, ...}]}``
"""

from __future__ import annotations

import ipaddress
from typing import Any

import httpx

from ....config import get_settings
from ...base import (
    Collector,
    DeviceManagement,
    DiscoveredClient,
    DiscoveredDevice,
    DiscoveredLink,
    DiscoveryResult,
)
from .models import MANUFACTURER, role_from_model, status_from_state


def _usable_primary_ip(raw_ip: str | None) -> str | None:
    """Return ``raw_ip`` only if it's a private address usable as the device's primary IP.

    UniFi reports a gateway's **WAN** IP in ``ipAddress`` and exposes no LAN/management IP via the
    Integration API — a gateway's device detail carries only physical ``interfaces.ports`` (link
    state/speed/PoE), no addresses (see #120). A public WAN address is not a management IP, so it
    must not become the NetBox ``primary_ip4`` (which drives Ansible's ``ansible_host``). Switches
    and APs report their private management IP in this same field, so they are unaffected.
    """
    if not raw_ip:
        return None
    try:
        addr = ipaddress.ip_address(raw_ip.split("/")[0].strip())
    except ValueError:
        return None
    if addr.is_private and not addr.is_loopback and not addr.is_link_local:
        return raw_ip
    return None


def _management(device: dict[str, Any]) -> DeviceManagement | None:
    """Pull management-plane facts (ADR-0010) out of a UniFi device payload, or None.

    The raw device ``state`` is normalized to a NetBox status token at observe time
    (``status_from_state``); the unmapped raw value stays available under ``device.raw``.
    """
    mgmt = DeviceManagement(
        status=status_from_state(device.get("state")),
        serial=device.get("serial"),
        firmware=device.get("version") or device.get("firmwareVersion"),
    )
    if mgmt.status or mgmt.serial or mgmt.firmware:
        return mgmt
    return None


def _pick_site(sites: list[dict[str, Any]], reference: str) -> dict[str, Any] | None:
    for site in sites:
        if site.get("internalReference") == reference:
            return site
    return sites[0] if sites else None


# UNIFI_SITE values (case-insensitive, stripped) that mean "discover every site".
_ALL_SITES = ("", "*", "all")


def _target_sites(sites: list[dict[str, Any]], reference: str) -> list[dict[str, Any]]:
    """Resolve which sites to discover from the ``UNIFI_SITE`` reference.

    Empty / ``*`` / ``all`` (case-insensitive, stripped) → every site the controller returned
    (opt-in multi-site). Any other value → the single matching site via :func:`_pick_site`
    (exact ``internalReference`` match, first-site fallback), preserving today's single-site
    behavior. Returns ``[]`` when the controller returned no sites.
    """
    if not sites:
        return []
    if reference.strip().lower() in _ALL_SITES:
        return list(sites)
    site = _pick_site(sites, reference)
    return [site] if site is not None else []


async def _get(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    response = await client.get(url)
    response.raise_for_status()
    data: dict[str, Any] = response.json()
    return data


async def _collect_site(
    client: httpx.AsyncClient, base: str, site: dict[str, Any], result: DiscoveryResult
) -> None:
    """Discover one UniFi site's devices, clients, and (per-site) topology into ``result``.

    Topology is resolved **strictly within this site**: a UniFi ``uplink.deviceId`` references a
    device in the same site, so the id→name map is built from this site's devices only — a
    cross-site map could mis-link on id collisions. Clients and per-device topology are
    best-effort (logged, never fatal); only a failed ``/devices`` fetch raises ``httpx.HTTPError``,
    which the caller isolates per site.
    """
    site_name = site.get("name") or site.get("internalReference")
    site_id = site["id"]

    devices = (await _get(client, f"{base}/sites/{site_id}/devices")).get("data", [])

    # Clients are best-effort: a controller without the endpoint still yields devices.
    try:
        clients = (await _get(client, f"{base}/sites/{site_id}/clients?limit=200")).get("data", [])
    except httpx.HTTPError as exc:
        clients = []
        result.notes.append(f"UniFi clients endpoint unavailable for site '{site_name}': {exc}")

    # Topology (best-effort): each device's detail carries its uplink device id (same site).
    uplinks: dict[str, str] = {}
    for device in devices:
        did = device.get("id")
        if not did:
            continue
        try:
            detail = await _get(client, f"{base}/sites/{site_id}/devices/{did}")
        except httpx.HTTPError:
            continue
        remote = (detail.get("uplink") or {}).get("deviceId")
        if remote:
            uplinks[did] = remote

    for device in devices:
        name = device.get("name") or device.get("mac") or "unknown"
        raw_ip = device.get("ipAddress") or device.get("ip")
        primary_ip = _usable_primary_ip(raw_ip)
        if raw_ip and not primary_ip:
            result.notes.append(
                f"{name}: ignoring non-private ipAddress {raw_ip} as primary "
                f"(UniFi reports the WAN IP; no management IP available — see #120)."
            )
        result.devices.append(
            DiscoveredDevice(
                name=name,
                mac=device.get("mac"),
                primary_ip=primary_ip,
                site=site_name,
                role=role_from_model(device.get("model")),
                model=device.get("model"),
                manufacturer=MANUFACTURER,
                management=_management(device),
                raw=device,
            )
        )
        if primary_ip:
            result.ip_addresses.append(primary_ip)

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

    # Resolve uplinks to names using THIS site's id map only (never cross-site).
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
                targets = _target_sites(sites, settings.unifi_site)
                if not targets:
                    result.notes.append("No UniFi sites returned by the controller.")
                    return result
                # Best-effort per site: one site's failed fetch is noted, the rest still run.
                for site in targets:
                    try:
                        await _collect_site(client, base, site, result)
                    except httpx.HTTPError as exc:
                        name = site.get("name") or site.get("internalReference")
                        result.notes.append(f"UniFi site '{name}' discovery failed: {exc}")
                result.notes.append(
                    f"Discovered {len(result.devices)} device(s), {len(result.clients)} "
                    f"client(s), {len(result.links)} link(s) across {len(targets)} UniFi site(s)."
                )
        except httpx.HTTPError as exc:
            result.notes.append(f"UniFi API request failed: {exc}")
            return result

        return result
