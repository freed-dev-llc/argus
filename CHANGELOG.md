# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.2] - 2026-06-18

### Changed

- Renamed the **PyPI distribution** to `argus-netbox` — the importable package and console
  scripts remain `argus` / `argus-mcp` / `argus-http`. (`argus` was already taken on PyPI by an
  unrelated project; `v0.1.1` published GHCR images + a GitHub Release but not PyPI.) `v0.1.2` is
  the first PyPI release.

## [0.1.1] - 2026-06-18

### Added

- **Dashboard auth passthrough** (P5): the bundled `argus-web` nginx now forwards the
  bearer token on its `/api` proxy, so the dashboard keeps working against an auth-enabled
  API. `web/nginx.conf` became `web/nginx.conf.template` (consumed via the official nginx
  image's `envsubst` templating) and injects `Authorization: Bearer ${HTTP_TOKEN}` on
  `/api` only — `/health` and the SPA fallback are untouched. `HTTP_TOKEN` is always
  defined in the web image (default empty), and compose passes the same `.env` value to
  `argus-web` as to `argus-server`. This resolves the open nginx Known Gap left when HTTP
  bearer auth landed: the default no-token deploy is unchanged (it forwards an empty bearer
  the server ignores).

- **Scheduled discovery + drift alerting** (P4): an opt-in, dependency-free in-process
  asyncio loop runs a discovery collector on a fixed interval, diffs it against NetBox, and
  records the latest outcome. Enable it with `SCHEDULE_INTERVAL` (seconds; `0`/unset =
  disabled) and pick the collector with `SCHEDULE_COLLECTOR` (default `unifi`). The result is
  exposed at `GET /api/drift/status` (under the existing bearer-auth gate) plus a structured
  log line each cycle. Setting `ALERT_WEBHOOK_URL` also POSTs a Slack-compatible
  `{"text": ...}` alert — but only when drift is present and the URL is set; a failed alert
  is swallowed and logged, never crashing the cycle. Strictly read-only: no reconcile or
  NetBox write is triggered. The loop is started from the FastAPI lifespan and is a no-op
  when disabled, so existing deployments are unaffected.
- **NetBox webhook classify + log** (P4): `POST /webhooks/netbox` now parses each NetBox
  change event into a structured `NetBoxEvent` (`event`, `model`, `object_id`, `display`,
  `username`, `request_id`, `timestamp`), emits a greppable structured log line, and acks
  with the classification (still includes `received: True`). Parsing is total/defensive —
  a malformed or non-dict payload never raises. Observability only: no discovery, reconcile,
  or NetBox write is triggered. Known gap: NetBox's `X-Hook-Signature` HMAC is not verified
  yet (authenticity relies on the optional `HTTP_TOKEN` bearer auth).
- **HTTP bearer-token auth** (P5): optional static bearer-token authentication on the
  FastAPI server. Set `HTTP_TOKEN` to require `Authorization: Bearer <token>` on every
  `/api/*` and `/webhooks/*` route (constant-time compare); `/health` and `/health/deep`
  stay public, and an unset token leaves the API open (back-compat / dev). CORS preflight
  (`OPTIONS`) is exempt so the dashboard/dev server keeps working, and the `Bearer` scheme
  is matched case-insensitively. When a token is set, NetBox webhooks must be configured to
  send the matching `Authorization` header.

### Changed

- **Example env files kept current**: `server/.env.example` and `deploy/.env.example` now
  include the loop's new optional settings (`HTTP_TOKEN`, `SCHEDULE_INTERVAL`,
  `SCHEDULE_COLLECTOR`, `ALERT_WEBHOOK_URL`) — all empty/placeholder — with "copy to `.env`,
  never commit real secrets" headers. `.env` stays gitignored (`.env` / `.env.*`, with
  `!.env.example`); no real secret is, or ever was, tracked.

## [0.1.0] - 2026-06-17

First tagged checkpoint: the full discover → diff → confirm → reconcile loop, validated
end-to-end against a live UniFi network + NetBox 4.6, with a dashboard, Docker deployment,
and Ansible integration.

### Added

- **UniFi-native topology** (#8): the UniFi collector captures device uplinks from the
  Integration API as `DiscoveredLink` edges (no SNMP needed). New `network_topology` tool +
  `GET /api/topology` return nodes + links, and the dashboard topology map now draws the
  uplink/neighbor edges between devices.
- **SNMP/LLDP collector** (#8): generic `snmp_lldp` collector for non-UniFi gear — SNMP GET
  `sysName` per target + an LLDP-MIB neighbor walk for links. Configured via `SNMP_TARGETS`
  (`host[:community],...`) / `SNMP_COMMUNITY`; needs the `discovery` extra (pysnmp). Closes #8.
- **Ansible deploy role** (`ansible/roles/argus_deploy` + `deploy-argus.yml`): stands up the
  full stack on a Docker host — repo checkout, `deploy/.env` rendering, and `docker compose up`
  via `community.docker.docker_compose_v2`. Secrets are generated once and **reused** from the
  existing `.env`, so re-runs never rotate the NetBox DB password / API token. Replaces the
  manual rsync + secret-gen + compose steps.
- **Ansible dynamic inventory** (`ansible/`): read-only `netbox.netbox.nb_inventory` config
  that sources hosts from the NetBox SoT Argus populates — grouped by site/role/manufacturer/
  etc., with `ansible_host` set to each device's primary IP. Includes a demo playbook,
  `requirements.yml`, and ADR-0004 (NetBox as the inventory hub + the two-writers rule). This
  is the outbound half of the loop: discover → NetBox → Ansible consumes.
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

- Reconcile diff is now **idempotent** for devices: NetBox device `site`/`role`/`primary_ip`
  are read as resolved slugs/addresses instead of pynetbox `.serialize()`'s bare FK integer
  IDs, so an already-synced device no longer shows perpetual phantom `update`s. Also gives
  the dashboard human-readable values. Surfaced by live validation.
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

[Unreleased]: https://github.com/freed-dev-llc/argus/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/freed-dev-llc/argus/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/freed-dev-llc/argus/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/freed-dev-llc/argus/releases/tag/v0.1.0
