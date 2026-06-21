# TODO

Tracked, actively-scoped work for Argus. Each item links a GitHub issue; phase context lives
in [docs/ROADMAP.md](docs/ROADMAP.md). Vendor-specific pack work (non-UniFi) is tracked in the
packs' own repos, not here.

## Features

- [ ] Webhook reactions — trigger discovery/reconcile on NetBox events (P4) — [#72](https://github.com/freed-dev-llc/argus/issues/72)
- [ ] Reconcile: broaden drift comparison beyond `primary_ip`/`site`/`role` — [#74](https://github.com/freed-dev-llc/argus/issues/74)
- [ ] Validate the generic SNMP/LLDP collector against live non-UniFi gear — [#75](https://github.com/freed-dev-llc/argus/issues/75)
- [ ] Scope & implement the vendor-pack `practices` extension point — [#77](https://github.com/freed-dev-llc/argus/issues/77)

## Add-ons

- [ ] Surface vendor-pack `capabilities`/`transport` in `list_collectors` — [#76](https://github.com/freed-dev-llc/argus/issues/76)
- [ ] Expose maintenance devtools (`argus-release`, …) as MCP tools — [#78](https://github.com/freed-dev-llc/argus/issues/78)

## Fixes / hardening

- [ ] Webhook: verify NetBox `X-Hook-Signature` (HMAC) — [#71](https://github.com/freed-dev-llc/argus/issues/71)
- [ ] Reconcile: drop IPv4 / `/32` / hardcoded `mgmt`-interface assumptions in primary-IP assignment — [#73](https://github.com/freed-dev-llc/argus/issues/73)
- [ ] Fix stale `netbox/client.py` "reads-only" docstring — [#79](https://github.com/freed-dev-llc/argus/issues/79)

## Notes (deliberate — not bugs)

- `dhcp_arp` collector is a deliberate stub, superseded by UniFi client discovery.
- The scheduled-drift loop is intentionally read-only (diff only; never `apply`).
- Vendor packs attach out-of-tree via the `argus.vendor_packs` entry point; additional packs
  live in their own repos (public or private) — see [docs/VENDOR_PACKS.md](docs/VENDOR_PACKS.md)
  and [ADR-0005](docs/architecture/adr/0005-vendor-packs.md).
- The **public open-source flip** (repo visibility) is held for Jon (P5).
