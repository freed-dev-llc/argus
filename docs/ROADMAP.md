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
  unset = open. (nginx token-forwarding for the bundled dashboard tracked with publishing.)
- Container image publishing (GHCR) and PyPI.
- Docs pass, examples, and the public open-source flip.
