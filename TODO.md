# TODO

Tracked, actively-scoped work for Argus. Each item links a GitHub issue; phase context lives
in [docs/ROADMAP.md](docs/ROADMAP.md). Vendor-specific pack work (non-UniFi) is tracked in the
packs' own repos, not here.

## Features

- [x] Webhook reactions — read-side only: event-triggered drift, never auto-apply ([ADR-0011](docs/architecture/adr/0011-webhook-reactions-read-side-only.md)) — [#72](https://github.com/freed-dev-llc/argus/issues/72)
- [x] Reconcile: broaden drift comparison to `device_type`/`manufacturer` (slug-normalized; status/serial/platform → discovery-first [#119](https://github.com/freed-dev-llc/argus/issues/119)) — [#74](https://github.com/freed-dev-llc/argus/issues/74)
- [x] Reconcile: drift-compare device `serial` (ADR-0010 write-back; `status`/`platform` still deferred) — [#119](https://github.com/freed-dev-llc/argus/issues/119)
- [ ] Validate the generic SNMP/LLDP collector against live non-UniFi gear — [#75](https://github.com/freed-dev-llc/argus/issues/75)
- [x] Scope & implement the vendor-pack `practices` extension point — [#77](https://github.com/freed-dev-llc/argus/issues/77) (shipped in v0.1.6, [ADR-0009](docs/architecture/adr/0009-vendor-pack-practices-spi.md))
- [ ] Multi-tenant (shared NetBox): stamp `tenant` on reconciled objects (`NETBOX_TENANT`) — [ADR-0007](docs/architecture/adr/0007-multi-tenant-netbox.md), [#86](https://github.com/freed-dev-llc/argus/issues/86)

## Add-ons

- [ ] Surface vendor-pack `capabilities`/`transport` in `list_collectors` — [#76](https://github.com/freed-dev-llc/argus/issues/76)
- [ ] Expose maintenance devtools (`argus-release`, …) as MCP tools — [#78](https://github.com/freed-dev-llc/argus/issues/78)

## Fixes / hardening

- [x] Webhook: verify NetBox `X-Hook-Signature` (HMAC) — [#71](https://github.com/freed-dev-llc/argus/issues/71) (done in [#111](https://github.com/freed-dev-llc/argus/pull/111))
- [x] Reconcile: family-aware primary-IP assignment (IPv6 → `primary_ip6`/`/128`, configurable `RECONCILE_MGMT_INTERFACE`; prefix-derivation deferred) — [#73](https://github.com/freed-dev-llc/argus/issues/73)
- [x] Fix stale `netbox/client.py` "reads-only" docstring — [#79](https://github.com/freed-dev-llc/argus/issues/79) (done in [#101](https://github.com/freed-dev-llc/argus/issues/101))

## Notes (deliberate — not bugs)

- `dhcp_arp` collector is a deliberate stub, superseded by UniFi client discovery.
- The scheduled-drift loop is intentionally read-only (diff only; never `apply`).
- Vendor packs attach out-of-tree via the `argus.vendor_packs` entry point; additional packs
  live in their own repos (public or private) — see [docs/VENDOR_PACKS.md](docs/VENDOR_PACKS.md)
  and [ADR-0005](docs/architecture/adr/0005-vendor-packs.md).
- The **public open-source flip** (repo visibility) is held for Jon (P5).
