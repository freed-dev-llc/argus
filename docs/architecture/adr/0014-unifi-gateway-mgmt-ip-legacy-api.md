# ADR-0014: UniFi Gateway Management IP via the Legacy Network API

- **Status:** Accepted
- **Date:** 2026-06-29
- **Deciders:** Jon Freed
- **Affected:** `server/src/argus/discovery/vendors/unifi/collector.py`
  (`_legacy_mgmt_ips`, `_needs_legacy_recovery`, `_usable_primary_ip`, `_management`)
- **Related:** [ADR-0010](0010-management-plane-contract.md) (management-plane `mgmt_ip`),
  [ADR-0005](0005-vendor-packs.md) (vendor packs / transport), [ADR-0003](0003-discovery-reconciliation-model.md)
  (read-only discovery, confirmation-gated reconcile)

## Context

A UniFi gateway (UDM/UXG/UCG) reports only its **public/CGNAT WAN IP** in the Integration API's
device `ipAddress`. The #120/#128 guard (`_usable_primary_ip`) correctly refuses that as the NetBox
`primary_ip4` — a WAN address is not a management IP and would mis-point Ansible's `ansible_host` —
but that leaves the gateway with **no** primary IP at all. The Integration API
(`{UNIFI_URL}/proxy/network/integration/v1`) exposes no gateway LAN/management address **anywhere**:
the device list and device detail carry only physical `interfaces.ports` (link state/speed/PoE),
and `/networks` is VLAN metadata. Switches and APs are unaffected — they report their private
management IP in the same `ipAddress` field.

A live, read-only spike (this session) confirmed that the **legacy** UniFi Network API answers to the
**same** `X-API-KEY` (no separate login): `GET {UNIFI_URL}/proxy/network/api/s/{site}/stat/device`
returns `{"data": [{...}]}` where the gateway's row carries a dedicated `lan_ip` field (its LAN/management
address). Integration devices can be matched to legacy rows by MAC.

## Decision

1. **Recover the gateway's LAN IP from the legacy `stat/device` endpoint, field `lan_ip`.** When a
   site has a gateway whose Integration `ipAddress` is not a usable primary, perform **one**
   best-effort `GET {root}/proxy/network/api/s/{internalReference}/stat/device` (where `root =
   UNIFI_URL` with no trailing slash), build a normalized `mac → lan_ip` map, and prefer the recovered
   `lan_ip` as both the gateway's `primary_ip` and `DeviceManagement.mgmt_ip` (ADR-0010).
2. **Same client, same key, no new config.** The legacy call reuses the collector's existing
   authenticated `httpx.AsyncClient` (`X-API-KEY` + `verify=unifi_verify_ssl`). No new endpoint
   credentials, no TLS-verify change, and **no new config flag** (a kill-switch was declined at GATE 1).
3. **Conditional, at most once per site.** The legacy fetch fires only when a site has ≥1 device that
   is a `gateway` (`role_from_model`) whose `_usable_primary_ip(ipAddress)` is `None`. No such gateway →
   no legacy call, so unrelated discovery runs never touch the legacy surface.
4. **Best-effort, never fatal.** The legacy GET is wrapped in `try/except httpx.HTTPError`; a missing
   endpoint (older/newer controller), auth, or transport failure is noted in `result.notes` and
   discovery falls back to today's behavior (gateway gets no primary). Only usable private (non-CGNAT,
   non-loopback, non-link-local) `lan_ip`s enter the map.
5. **Deterministic CGNAT rejection.** `_usable_primary_ip` rejects `100.64.0.0/10` (RFC 6598)
   explicitly, before the `is_private` check, because the stdlib `ipaddress` classification of that
   range is version-sensitive (`is_private=False` on the targeted CPython, `True` on some patch
   levels). An ISP-assigned CGNAT WAN is therefore always refused as primary.

## Rationale

- **`lan_ip` is direct and sufficient.** The legacy row already carries the management address;
  deriving it from `networkconf`/`ip_subnet` would be more code for the same answer (deferred — see
  Consequences).
- **Same key / read-only** keeps the safety model intact: discovery stays read-only against the
  network (ADR-0003), and the recovered IP becomes a NetBox primary only through the existing
  confirmation-gated reconcile, exactly as a switch/AP primary does.
- **Conditional + best-effort** bounds both the blast radius (only recovery-needing gateways hit the
  legacy endpoint) and the risk (an unofficial endpoint that is absent on some controller versions
  can never break discovery).
- **Explicit CGNAT reject** makes the classification deterministic across Python versions, so the
  same WAN is rejected in dev, CI, and production regardless of patch level.

## Consequences

- A gateway whose only Integration IP is its WAN now gets a correct management primary IP when the
  legacy API provides it; reconcile can assign it as `primary_ip4` (driving `ansible_host`).
- Argus now depends, **best-effort**, on an **unofficial, version-sensitive** controller surface
  (`/proxy/network/api/.../stat/device`). It is never required: a controller without it still
  completes discovery, with a note. If a future controller changes or removes the endpoint, the only
  regression is "gateway has no primary IP again" — the prior, already-handled state.
- `DeviceManagement.mgmt_ip` is now populated for recovered gateways. It is additive metadata
  (ADR-0010); reconcile does not consume `mgmt_ip` directly — the user-visible effect comes from
  `primary_ip`, which reconcile already maps to `assign_primary_ip`.

## Alternatives Considered

- **Derive the LAN IP from `networkconf` / `ip_subnet`.** More indirection for the same value;
  `lan_ip` is the direct field. Deferred as a future enrichment, not needed now.
- **A new config flag / kill-switch for the legacy call.** Declined at GATE 1 — the call is already
  conditional and best-effort, so a flag adds surface without changing the safety posture.
- **Treat the CGNAT WAN as usable (rely on `is_private`).** Rejected — version-fragile and wrong:
  a CGNAT WAN is not a management IP.
- **Leave the gateway with no primary IP (status quo after #128).** Rejected — the management IP is
  recoverable and is exactly what NetBox/Ansible need.

## References

- [ADR-0010](0010-management-plane-contract.md) — management-plane → NetBox contract (`mgmt_ip`).
- [ADR-0005](0005-vendor-packs.md) — vendor packs / transport boundary.
- [ADR-0003](0003-discovery-reconciliation-model.md) — read-only discovery, confirmation-gated reconcile.
- Issue #129 (this change); builds on #120/#128 (WAN-IP guard).
