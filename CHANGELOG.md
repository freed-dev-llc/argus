# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Docker deployment** (`deploy/`): a self-contained validation stack — bundled NetBox
  (own internal Postgres/Redis) + `argus-server` + `argus-web` (nginx serving the built
  dashboard, proxying `/api`). A `netbox-init` one-shot provisions a **v1** NetBox API token
  for Argus (NetBox 4.6 v2 tokens use a `Bearer <key>.<token>` scheme pynetbox can't present).
  Plus a multi-stage `web/Dockerfile`, `nginx.conf`, and `.dockerignore`s. One `docker compose up`.
  Validated end-to-end against live UniFi + NetBox 4.6.
- **IPAM prefix hierarchy** in the dashboard: builds a containment tree from
  `GET /api/prefixes` and renders it indented (CIDR + status + description). IPv4 prefixes
  nest by containment; IPv6/unparseable fall back to flat roots. Completes the P3 "IPAM
  hierarchy" item.
- **Topology map** in the dashboard (#11): replaces the placeholder with an SVG view of
  NetBox devices grouped by site and colored by role (with primary IPs). Dependency-free;
  real link edges (cabling / LLDP neighbors) and a graph library are deferred until a
  collector provides neighbor data (#8).
- **UniFi client discovery → IPAM**: the UniFi collector now also pulls connected clients
  (IP / MAC / hostname) from the Integration API `/clients` endpoint (best-effort — devices
  still discover if it's absent), and the reconcile engine proposes/creates NetBox **IPAM IP
  addresses** for client IPs it doesn't yet have. Covers much of what a DHCP/ARP collector
  would, using the UniFi API already in use. `DiscoveryResult` gains `clients`.
- **Web drift panel**: the dashboard now shows reconcile drift (proposed create/update
  changes with field deltas) and drives the two-step **confirm → apply** flow via
  `GET /api/drift` and `POST /api/reconcile`, rendering per-change apply results.
- **NetBox write & FK-resolution** for reconcile apply: `apply` now *persists* — it
  find-or-creates the supporting NetBox objects (site, device role, manufacturer, device
  type) and assigns the primary IPv4 (management interface + IPAM object), so discovered
  devices are actually created/updated. `site` and `role` are reconciled alongside
  `primary_ip`; discovery now carries `model`/`manufacturer`. Closes #29.
- **Reconcile engine** (`ReconcileEngine`): diffs observed devices against NetBox
  (match by name → `create` for unknown devices, `update` for primary-IP drift; NetBox-only
  devices reported, never auto-deleted) and applies a plan through a confirmation-gated,
  per-change write path. `drift_report` and `reconcile_apply` now run a collector + diff
  against live NetBox; `GET /api/drift` and `POST /api/reconcile` expose them. Resolving
  discovery values into NetBox foreign keys (sites/roles/device-types/IPs) is a follow-up.
  Closes #10.
- **UniFi discovery collector** (`discovery_scan unifi`): pulls devices from the UniFi
  Network Integration API (X-API-KEY) and normalizes them to `DiscoveredDevice`
  (name/mac/primary_ip/site + coarse role inference from model). Configured via
  `UNIFI_URL` / `UNIFI_API_TOKEN` / `UNIFI_SITE`. Closes #7.
- Initial monorepo scaffold for **Argus**, a NetBox-backed network source-of-truth
  automation server for MCP coding agents.
- **Server** (`server/`): Python MCP (stdio) + FastAPI HTTP server.
  - NetBox read tools via `pynetbox`: `list_devices`, `get_device`, `list_prefixes`,
    `list_ip_addresses`, `search`.
  - Pluggable discovery layer (`Collector` interface) with stubbed UniFi, SNMP/LLDP,
    and DHCP/ARP collectors.
  - Reconciliation engine skeleton (dry-run by default) and confirmation-gated
    `reconcile_apply` tool.
  - FastAPI endpoints (`/health`, `/api/devices`, `/api/prefixes`, `/api/drift`,
    `/webhooks/netbox`) consumed by the web app.
- **Web** (`web/`): React + Vite + TypeScript dashboard shell (device table, drift
  panel, topology-map placeholder).
- Governance: ADRs (0001–0003), architecture and roadmap docs, CI, Dependabot
  auto-merge, issue/PR templates, and the `freed-dev-llc` repo baseline.

### Fixed

- UniFi role inference now matches full model names (e.g. `UniFi Dream Machine PRO SE` →
  `gateway`) via keyword matching instead of code prefixes, so gateways are classified and
  reconciled instead of skipped. Surfaced by live validation against a real UniFi controller.

### Dependencies

- Consolidated the initial Dependabot pile-up into one upgrade: server floors
  (`httpx`, `pydantic`, `pytest-cov`, `ruff`, `mypy`), web (`typescript` 6, `globals` 17,
  `eslint-plugin-react-refresh` 0.5), and GitHub Actions (`checkout`, `setup-python`,
  `setup-node`, `action-gh-release` majors).
- Deferred frontend toolchain majors via `dependabot.yml` ignores: `@vitejs/plugin-react`
  6 (needs vite 8) and `eslint` / `@eslint/js` 10 (not yet supported by typescript-eslint).

[Unreleased]: https://github.com/freed-dev-llc/argus/commits/main
