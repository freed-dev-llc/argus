# Roadmap

Phased plan. Each phase is a set of GitHub issues; architectural choices get an ADR.

## P0 — Scaffold ✅ (this cut)

- Monorepo: Python MCP/FastAPI server + React/Vite/TS web app.
- NetBox read tools (`pynetbox`) wired through MCP + HTTP.
- Pluggable discovery + reconciliation interfaces (stubbed).
- Governance: ADRs, CHANGELOG, CI, Dependabot, issue/PR templates.

## P1 — Observe the real network

- ✅ **UniFi collector** (#7): devices, plus connected **clients** (IP/MAC/hostname) feeding
  NetBox IPAM via reconcile — covers much of the DHCP/ARP intent using the UniFi API.
- ✅ Normalized collector output (`DiscoveryResult`: devices + clients).
- ✅ **SNMP/LLDP** (#8): UniFi-native uplink topology (validated live) + a generic pysnmp
  collector for non-UniFi gear (unvalidated vs live SNMP). **DHCP/ARP** (#9): closed —
  covered by UniFi client discovery.
- ✅ Web: device table populated from live NetBox data.

## P2 — Reconcile

- ✅ `ReconcileEngine.diff()`: compare observed state vs NetBox, emit a typed plan (#10).
- ✅ `apply()` with confirmation gating and per-change dispatch (#10).
- ✅ `drift_report` / `reconcile_apply` run a collector + diff against live NetBox; exposed
  at `GET /api/drift` and `POST /api/reconcile`.
- ✅ **P2.1 — NetBox write FK-resolution** (#29): `apply` find-or-creates sites, device
  roles, manufacturers, and device types, and assigns primary IPs via IPAM, so create/update
  persist. Web drift panel wired — view drift + run confirm→apply from the dashboard.

## P3 — Visualize

- ✅ Topology map in the web app (#11): devices grouped by site, colored by role (SVG,
  dependency-free). Decision: defer `react-flow`/`cytoscape` until there are real edges.
- ✅ IPAM prefix hierarchy: containment tree from `/api/prefixes`, rendered indented.
- ✅ Topology **edges**: UniFi-native uplink/neighbor links (#8) drawn on the map via
  `GET /api/topology`. (Generic SNMP/LLDP edges for non-UniFi gear: see #8.)

## P4 — Stay current automatically

- NetBox webhooks (`/webhooks/netbox`):
  - ✅ **classify + structured-log** change events (event / model / object / actor), defensive
    parsing into a `NetBoxEvent`. Observability half of P4.
  - reacting/automating on events (discovery trigger / reconcile) — deferred.
- ✅ **Scheduled discovery + drift alerting**: opt-in, dependency-free in-process asyncio
  scheduler (`SCHEDULE_INTERVAL`, off by default) runs discovery + diff on an interval, records
  the latest drift at `GET /api/drift/status`, structured-logs it, and fires an optional
  Slack-compatible webhook (`ALERT_WEBHOOK_URL`) on drift. Read-only (diff, no `apply`).

## P5 — Hardening & open source

- ✅ Deployment story: self-contained `deploy/` compose bundling NetBox + Argus server + web.
- ✅ **HTTP auth** on the Argus server/API: optional static bearer token (`HTTP_TOKEN`),
  enforced when set — `/api` + `/webhooks` gated (constant-time compare), health public,
  unset = open. The bundled dashboard's nginx forwards the token, so it works against an
  auth-enabled API.
- ✅ **Container image publishing (GHCR) + PyPI**: a `v*` tag pushes
  `ghcr.io/freed-dev-llc/argus-server` + `argus-web` images and publishes the server to PyPI
  (distribution `argus-netbox`, import `argus`) via trusted publishing (OIDC).
- ✅ **Release tooling** (`argus-release`, `argus.devtools.release`): a manifest-driven,
  unit-tested devtool that bumps every version reference from `release.toml`, cuts the
  CHANGELOG, and verifies the build — one command per release instead of a hand-done multi-file
  edit. Latest release: **0.1.7** (PyPI `argus-netbox` + GHCR images).
- ✅ Docs pass + examples (this step).
- The **public open-source flip** (repo visibility) — still pending, held for Jon.

## P6 — Multi-vendor extensibility (vendor packs)

- ✅ **Vendor-pack host/plugin layer** ([ADR-0005](architecture/adr/0005-vendor-packs.md)): a
  `VendorPack` bundles a read-only collector with declarative metadata (manufacturer, transport,
  capabilities, config vars) + model→role normalization. The registry merges built-in packs with
  **external packs** discovered via an `argus.vendor_packs` entry point, so packs ship out-of-tree
  (public or private) with no change to Argus. `COLLECTORS` derives from it; name lookup unchanged.
- ✅ **UniFi refactored into the first in-tree pack** (`discovery/vendors/unifi/`,
  behaviour-preserving).
- ✅ **Pack template**: public GitHub "Use this template" repo
  [`argus-vendor-pack-template`](https://github.com/freed-dev-llc/argus-vendor-pack-template).
- Surface pack `capabilities`/`transport` in `list_collectors` so agents can see what each pack
  can discover.
- ✅ **Practices SPI** ([ADR-0009](architecture/adr/0009-vendor-pack-practices-spi.md)): the
  `practices` (best-practice / validation) extension point ADR-0005 reserved. A `Practice`
  evaluates a `PracticeContext` (observed `DiscoveryResult` + read-only NetBox snapshot) and
  returns `Finding`s; surfaced advisory/read-only via `evaluate_practices` (MCP) + `GET
  /api/practices`. UniFi ships the reference rules.
- Validate the generic non-UniFi SNMP/LLDP collector against live gear; per-device (SNMP/SSH)
  transport packs.
- Additional vendor packs ship in their own repos (public or private) via the entry point.
- ✅ **Management-plane read** ([ADR-0010](architecture/adr/0010-management-plane-contract.md)):
  per-vendor `management` work starts with read-only management-plane data — a typed
  `DeviceManagement` object on `DiscoveredDevice` that packs populate and `discovery_scan`
  surfaces (UniFi populates it). NetBox write-back of that data is a defined, confirmation-gated
  follow-up (pending).

## Beyond — active management (write-back)

Read-only discovery is the **current phase, not the end state**. A planned direction is
**active management**: writing config back to the network (via vendor packs), under the same
dry-run + confirmation-gating safety model as reconcile. The per-vendor `management` sub-issues
begin with read-only management-plane data and lead toward this. The language/runtime boundary —
Python brain, optional Go actuator — is recorded in
[ADR-0006](architecture/adr/0006-python-brain-go-actuator.md).
