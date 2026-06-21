# ADR-0005: Vendor Packs — a Host/Plugin Boundary for Per-Vendor Discovery

- **Status:** Accepted; UniFi refactored into the first in-tree pack + entry-point loader
  (this change). External/private packs (e.g. MSP-supported vendors) attach out-of-tree
  via the `argus.vendor_packs` entry point and are **not** part of this repo.
- **Date:** 2026-06-21
- **Deciders:** Jon Freed
- **Affected:** `server/src/argus/discovery/` (`vendors/`, `collectors/`), `tools/discovery_tools.py`
- **Related:** [ADR-0003](0003-discovery-reconciliation-model.md) (pluggable discovery)

## Context

ADR-0003 gave us a `Collector` ABC → normalized `DiscoveryResult` and a flat
`COLLECTORS` registry. That covers *how to acquire* state, but per-vendor knowledge —
manufacturer, model→role/device-type normalization, the config/credentials a source
needs, what it can discover, and (later) best-practice expectations — currently lives
hardcoded inside each collector (the UniFi collector pins `manufacturer="Ubiquiti"` and a
role-keyword table). Argus needs to grow to many vendors (UniFi at home; Aruba Central,
Juniper Mist, Cisco in a lab), and a flat collector list neither captures that metadata
nor makes adding a vendor a consistent, testable, drop-in unit.

There is also a **distribution constraint**: some vendor integrations are competitively
sensitive (built by/for a managed-service-provider context) and must stay private, while
others (UniFi) can be shared publicly. The architecture must let packs live — and be
licensed — in *different repositories with different visibility*, without the public host
ever containing or even naming the private set.

## Decision

1. **VendorPack** — a declarative descriptor bundling, per vendor: the `Collector`
   adapter plus `manufacturer`, `transport` (`controller_api` | `device_snmp` |
   `device_ssh`), `capabilities` (`devices`/`clients`/`topology`/`config`), `config_vars`
   (the settings it consumes), and model normalization. A `practices` field is reserved
   as the best-practice/validation extension point (empty for now). Defined in
   `discovery/vendors/pack.py`.
2. **Packs are self-contained modules** under `discovery/vendors/<name>/`
   (`collector.py`, `models.py`, optional `practices.py`, `__init__.py` exposing the
   pack instance).
3. **Host/plugin boundary.** The registry discovers packs from two sources:
   - **built-in** packs shipped in this repo (currently just UniFi), and
   - **external** packs from *any installed distribution* that advertises an
     **`argus.vendor_packs` entry point** resolving to a `VendorPack`.
   The legacy `COLLECTORS` map is *derived* from the merged set, so name-based lookup
   (`"unifi"`, the default in tools/config) is unchanged.
4. **Public SPI.** `Collector`, `DiscoveryResult`, the `Discovered*` DTOs, and
   `VendorPack`/`Transport` are the stable contract external packs import. They ship in
   the public `argus-netbox` distribution; private packs depend on it and nothing else
   of ours.
5. **Two transport shapes are first-class.** Controller/cloud-API packs (UniFi, Aruba
   Central, Mist, Meraki) where one API yields many devices, and per-device protocol
   packs (classic Cisco via SNMP/SSH). Both still emit one normalized `DiscoveryResult`,
   so reconcile (ADR-0003) is untouched.
6. **UniFi is the reference + the public pack.** It is refactored in-tree
   (behaviour-preserving) to lock the pattern; the MSP context does not support UniFi, so
   sharing it carries no competitive risk.

## Rationale

- Vendor specifics stay out of the engine and out of each other; adding a vendor is a
  self-contained, independently-testable module.
- Entry-point discovery is the proven host/plugin pattern (pytest, flake8, Datasette). It
  lets a **private** `argus-vendor-packs` distribution register Aruba/Mist/Cisco by being
  installed alongside Argus — the public repo holds none of that code and stays
  vendor-neutral about it (only UniFi is named publicly).
- Apache-2.0 is permissive: proprietary plugins built on the public SPI need no source
  disclosure, so the private packs stay closed, legitimately.
- Declarative metadata (`capabilities`, `config_vars`) is variable-driven, fitting the
  MCP/CI/Ansible control surfaces.

## Consequences

- `COLLECTORS` becomes derived; `UniFiCollector` moves to
  `discovery/vendors/unifi/collector.py` (re-exported from `discovery/collectors` for
  back-compat). Role/model inference moves to `discovery/vendors/unifi/models.py`.
- Built-in packs register directly (no install step needed for dev/CI); only *external*
  packs require the entry point — so the public test suite never depends on a private
  pack, and a broken external pack is skipped defensively rather than crashing discovery.
- New packs ship recorded API fixtures for offline tests (UniFi already does, via `respx`).
- **Open sub-decisions:** the scope of `practices` (naming / role classification /
  compliance) and the Cisco surface (Meraki vs Catalyst/DNA vs IOS-SNMP) are deferred to
  follow-up ADRs; the transport split accommodates whichever.

## Alternatives Considered

- **Keep enriching flat collectors.** Rejected — vendor metadata stays scattered and
  hardcoded, with no consistent home for manufacturer/capabilities/best-practices and no
  clean way to split public vs private.
- **One in-tree mega-package with all vendors.** Rejected — couples the public repo to
  competitively-sensitive code and to every vendor's dependencies.
- **Pack = collector only (no descriptor).** Rejected — loses the metadata bundling that
  is the point.
- **Git submodule for private packs.** Rejected in favour of an installed distribution +
  entry points — looser coupling, independent CI, normal dependency resolution.

## References

- [ADR-0003](0003-discovery-reconciliation-model.md) — pluggable discovery + reconcile.
- Python packaging entry points (`importlib.metadata`) — host/plugin discovery.
- Private companion distribution: `argus-vendor-packs` (separate repo, not published).
