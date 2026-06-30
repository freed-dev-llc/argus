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

# Carrier-grade NAT (RFC 6598) shared address space. An ISP hands a UniFi gateway one of these as
# its WAN address (Starlink, T-Mobile, etc.), so it is never a usable management IP. Rejected
# explicitly because ``ipaddress.is_private`` is version-fragile for this range (``False`` on the
# CPython this targets, ``True`` on some patch levels) — see ADR-0014 and #129.
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def _usable_primary_ip(raw_ip: str | None) -> str | None:
    """Return ``raw_ip`` only if it's a private address usable as the device's primary IP.

    UniFi reports a gateway's **WAN** IP in ``ipAddress`` and exposes no LAN/management IP via the
    Integration API — a gateway's device detail carries only physical ``interfaces.ports`` (link
    state/speed/PoE), no addresses (see #120). A public or CGNAT WAN address is not a management IP,
    so it must not become the NetBox ``primary_ip4`` (which drives Ansible's ``ansible_host``).
    Switches and APs report their private management IP in this same field, so they are unaffected.

    Order: parse → reject CGNAT (``100.64.0.0/10``, deterministic regardless of the running
    Python's ``is_private`` classification) → require private, non-loopback, non-link-local.
    """
    if not raw_ip:
        return None
    try:
        addr = ipaddress.ip_address(raw_ip.split("/")[0].strip())
    except ValueError:
        return None
    if addr in _CGNAT:
        return None
    if addr.is_private and not addr.is_loopback and not addr.is_link_local:
        return raw_ip
    return None


def _management(device: dict[str, Any], mgmt_ip: str | None = None) -> DeviceManagement | None:
    """Pull management-plane facts (ADR-0010) out of a UniFi device payload, or None.

    The raw device ``state`` is normalized to a NetBox status token at observe time
    (``status_from_state``); the unmapped raw value stays available under ``device.raw``.
    ``mgmt_ip`` is the recovered management/LAN IP, if any (gateway legacy-API recovery, #129);
    it counts toward the "any field learned?" gate so a device known only by its mgmt IP is kept.
    """
    mgmt = DeviceManagement(
        status=status_from_state(device.get("state")),
        serial=device.get("serial"),
        firmware=device.get("version") or device.get("firmwareVersion"),
        mgmt_ip=mgmt_ip,
    )
    if mgmt.status or mgmt.serial or mgmt.firmware or mgmt.mgmt_ip:
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


def _needs_legacy_recovery(devices: list[dict[str, Any]]) -> bool:
    """True if any device is a gateway whose Integration ``ipAddress`` isn't a usable primary.

    Gates the (at most one) legacy ``stat/device`` fetch per site (#129): a gateway reporting only
    its WAN address has no usable primary IP, so its LAN/management IP must be recovered from the
    legacy API. No such gateway → no legacy call (minimal API traffic; the conditional is also what
    keeps unrelated discovery runs from touching the legacy endpoint at all).
    """
    for device in devices:
        if role_from_model(device.get("model")) == "gateway":
            raw_ip = device.get("ipAddress") or device.get("ip")
            if _usable_primary_ip(raw_ip) is None:
                return True
    return False


async def _legacy_mgmt_ips(
    client: httpx.AsyncClient, root: str, site_ref: str
) -> dict[str, str]:
    """Best-effort ``mac → lan_ip`` map from the **legacy** UniFi Network API (#129, ADR-0014).

    The Integration API exposes no gateway LAN/management IP (a gateway's device detail carries only
    physical port state — see #120), so a gateway whose only Integration ``ipAddress`` is its WAN
    ends up with no primary IP. The older ``stat/device`` endpoint — an unofficial, version-sensitive
    controller surface that answers to the **same** ``X-API-KEY`` — returns a per-device ``lan_ip``
    we recover the management address from. Queries
    ``{root}/proxy/network/api/s/{site_ref}/stat/device`` reusing the caller's authenticated client.

    Returns ``mac.strip().lower() → lan_ip`` for every row whose ``lan_ip`` is a usable private
    address (:func:`_usable_primary_ip`). Read-only; propagates ``httpx.HTTPError`` to the caller,
    which treats a failure as best-effort (notes it and falls back to today's no-primary behavior),
    so a controller without the endpoint still completes discovery.
    """
    payload = await _get(client, f"{root}/proxy/network/api/s/{site_ref}/stat/device")
    mapping: dict[str, str] = {}
    for row in payload.get("data", []):
        mac = row.get("mac")
        lan_ip = _usable_primary_ip(row.get("lan_ip"))
        if mac and lan_ip:
            mapping[mac.strip().lower()] = lan_ip
    return mapping


async def _collect_site(
    client: httpx.AsyncClient, base: str, root: str, site: dict[str, Any], result: DiscoveryResult
) -> None:
    """Discover one UniFi site's devices, clients, and (per-site) topology into ``result``.

    Topology is resolved **strictly within this site**: a UniFi ``uplink.deviceId`` references a
    device in the same site, so the id→name map is built from this site's devices only — a
    cross-site map could mis-link on id collisions. Clients and per-device topology are
    best-effort (logged, never fatal); only a failed ``/devices`` fetch raises ``httpx.HTTPError``,
    which the caller isolates per site. ``root`` (``{UNIFI_URL}`` with no trailing slash) is the
    base for the conditional legacy ``stat/device`` mgmt-IP recovery (#129, ADR-0014).
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

    # Gateway mgmt-IP recovery (#129, ADR-0014): only when a gateway has no usable Integration
    # primary IP, fetch the legacy stat/device map once to recover its LAN IP by MAC. Best-effort —
    # a missing/failing legacy endpoint is noted and discovery falls back to today's behavior.
    legacy_mgmt: dict[str, str] = {}
    if _needs_legacy_recovery(devices):
        site_ref = site.get("internalReference")
        if site_ref:
            try:
                legacy_mgmt = await _legacy_mgmt_ips(client, root, site_ref)
            except httpx.HTTPError as exc:
                result.notes.append(
                    f"UniFi legacy stat/device unavailable for site '{site_name}': {exc} "
                    f"(gateway management IP not recovered — see #129)."
                )

    for device in devices:
        name = device.get("name") or device.get("mac") or "unknown"
        mac = device.get("macAddress") or device.get("mac")
        raw_ip = device.get("ipAddress") or device.get("ip")
        primary_ip = _usable_primary_ip(raw_ip)
        mgmt_ip: str | None = None
        if primary_ip is None and mac:
            recovered = legacy_mgmt.get(mac.strip().lower())
            if recovered:
                primary_ip = mgmt_ip = recovered
        if raw_ip and primary_ip is None:
            result.notes.append(
                f"{name}: ignoring non-private ipAddress {raw_ip} as primary "
                f"(UniFi reports the WAN IP; no management IP available — see #120)."
            )
        result.devices.append(
            DiscoveredDevice(
                name=name,
                mac=mac,
                primary_ip=primary_ip,
                site=site_name,
                role=role_from_model(device.get("model")),
                model=device.get("model"),
                manufacturer=MANUFACTURER,
                management=_management(device, mgmt_ip),
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

        root = settings.unifi_url.rstrip("/")
        base = root + "/proxy/network/integration/v1"
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
                        await _collect_site(client, base, root, site, result)
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
