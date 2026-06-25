# Argus

![Argus Net](docs/assets/argus/logos/argus_logo_horizontal.svg)

[![CI](https://github.com/freed-dev-llc/argus/actions/workflows/ci.yml/badge.svg)](https://github.com/freed-dev-llc/argus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/argus-netbox.svg)](https://pypi.org/project/argus-netbox/)
[![Python](https://img.shields.io/pypi/pyversions/argus-netbox.svg)](https://pypi.org/project/argus-netbox/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

> The all-seeing keeper of your network's truth.

**Argus** is a home- and lab-network automation server built on
[NetBox](https://netbox.dev). It treats NetBox as the **single source of truth (SoT)**
for your network and works to keep that truth *continuously reflecting reality* —
devices, IP addresses, prefixes, cabling, and topology — by **discovering** the live
network, **diffing** it against NetBox, and **reconciling** the difference.

Argus exposes this capability to **MCP-compliant coding agents** (Claude Code, Codex,
Kimi, …) as a set of tools, and ships a small React dashboard to query state, review
drift, and trigger reconciliation by hand.

In Greek myth, Argus Panoptes was the hundred-eyed giant who never slept and saw
everything. That's the job: always watching, always keeping the record true.

> **Status:** v0.1.7 — the full loop works end-to-end and is validated against a live UniFi
> network + NetBox 4.6: discover (devices, clients, uplink topology) → diff → confirm →
> reconcile NetBox (DCIM + IPAM), surfaced via MCP tools, a React dashboard, and Ansible
> inventory. See [docs/ROADMAP.md](docs/ROADMAP.md) and [CHANGELOG.md](CHANGELOG.md).

**Part of the freed-dev-llc agent family** — Argus is shared tooling for the AI assistants [Aria](https://github.com/freed-dev-llc/aria), [Leeloo](https://github.com/freed-dev-llc/leeloo), and [Elara](https://github.com/freed-dev-llc/elara); sibling tools are [Reach](https://github.com/freed-dev-llc/reach) (remote access), [Sisyphus](https://github.com/freed-dev-llc/sisyphus) (workflow automation), and [Mnemosyne](https://github.com/freed-dev-llc/mnemosyne) (RAG knowledge brain — it *explains* the vendors Argus *discovers*).

[![Aria — freed-dev-llc/aria](docs/assets/buttons/btn_aria.svg)](https://github.com/freed-dev-llc/aria)
[![Leeloo — freed-dev-llc/leeloo](docs/assets/buttons/btn_leeloo.svg)](https://github.com/freed-dev-llc/leeloo)
[![Elara — freed-dev-llc/elara](docs/assets/buttons/btn_elara.svg)](https://github.com/freed-dev-llc/elara)
[![Reach — freed-dev-llc/reach](docs/assets/buttons/btn_reach.svg)](https://github.com/freed-dev-llc/reach)
[![Sisyphus — freed-dev-llc/sisyphus](docs/assets/buttons/btn_sisyphus.svg)](https://github.com/freed-dev-llc/sisyphus)
[![Mnemosyne — freed-dev-llc/mnemosyne](docs/assets/buttons/btn_mnemosyne.svg)](https://github.com/freed-dev-llc/mnemosyne)
[![Helios — freed-dev-llc/helios](docs/assets/buttons/btn_helios.svg)](https://github.com/freed-dev-llc/helios)

## How it fits together

```
Collectors (UniFi / SNMP-LLDP / DHCP-ARP …) ─► normalize ─► diff vs NetBox ─► reconcile plan ─► apply
        (server/src/argus/discovery/)                          (reconcile/)     (dry-run default,
                                                                                 confirmation-gated)
NetBox ◄── pynetbox client ──► MCP tools (server/src/argus/tools/) ──► coding agents
                            └─► FastAPI (http_server.py) ──► React dashboard (web/)
```

NetBox is authoritative; Argus never invents truth — it makes NetBox match what it
observes. Writes are **dry-run by default** and real changes are **confirmation-gated**.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and the
[Architecture Decision Records](docs/architecture/adr/).

The HTTP server also keeps the record current on its own: it receives NetBox **webhooks**
(`POST /webhooks/netbox`, classify + structured-log) and can run an **opt-in scheduled drift
loop** (`SCHEDULE_INTERVAL`) that diffs on an interval — read-only — serving the latest result at
`GET /api/drift/status` and firing an optional alert webhook (`ALERT_WEBHOOK_URL`) on drift.
Optional **bearer-token auth** (`HTTP_TOKEN`) gates `/api` + `/webhooks`. See
[server/README.md](server/README.md) for setup and copy-pasteable examples.

**Vendor packs.** Discovery is a host/plugin layer
([ADR-0005](docs/architecture/adr/0005-vendor-packs.md)): each vendor is a self-contained
`VendorPack` (a read-only collector + declarative metadata) discovered via an
`argus.vendor_packs` entry point, so packs can live out-of-tree and ship independently.
UniFi ships in-tree; build your own from
[**argus-vendor-pack-template**](https://github.com/freed-dev-llc/argus-vendor-pack-template)
(a GitHub “Use this template” repo). See [docs/VENDOR_PACKS.md](docs/VENDOR_PACKS.md) to
install or add packs.

## Repository layout

| Path | What |
| --- | --- |
| `server/` | Python MCP + FastAPI server (`mcp`, `fastapi`, `pynetbox`) |
| `web/` | React + Vite + TypeScript dashboard |
| `docs/` | Architecture, roadmap, and ADRs |
| `.github/` | CI, Dependabot, issue/PR templates, CODEOWNERS |

## Quickstart

### Server

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Point Argus at your NetBox (see .env.example)
export NETBOX_URL="https://netbox.lan"
export NETBOX_TOKEN="<a NetBox API token>"

argus-http        # FastAPI on :8080  (used by the web app)
argus-mcp         # MCP server over stdio (used by coding agents)
```

If `NETBOX_URL` / `NETBOX_TOKEN` are unset, tools return a clear "NetBox not
configured" message rather than failing — handy for first-run exploration.

### Web dashboard

```bash
cd web
npm install
npm run dev       # http://localhost:5173 — proxies /api to the server on :8080
```

### Use from a coding agent (MCP)

`.mcp.json` at the repo root registers the `argus` server. With the package installed
(`pip install -e server`), Claude Code (and other MCP clients) can call:

- `list_devices`, `get_device`, `list_prefixes`, `list_ip_addresses`, `search` — read NetBox
- `list_collectors`, `discovery_scan`, `network_topology` — observe live network state + topology
- `drift_report`, `reconcile_apply` — review and apply reconciliation (confirmation-gated)
- `evaluate_practices` — run a collector's best-practice rules for advisory findings (read-only)

## Deployment

For a complete, self-contained environment (NetBox + its datastore + Argus server + web),
see [`deploy/`](deploy/README.md): `docker compose --env-file .env up -d --build` brings up
a bundled NetBox (auto-provisioned with the API token Argus uses) plus the Argus server and
dashboard. Intended for validation and home/lab use.

### Published artifacts

Released `v*` tags publish to GHCR and PyPI:

- **Container images** — `ghcr.io/freed-dev-llc/argus-server` and
  `ghcr.io/freed-dev-llc/argus-web` (tags `0.1.7` and `latest`):

  ```bash
  docker pull ghcr.io/freed-dev-llc/argus-server:0.1.7
  docker pull ghcr.io/freed-dev-llc/argus-web:0.1.7
  ```

- **Python package** — the server installs from PyPI as `argus-netbox` (the import package stays
  `argus`; the console scripts are `argus-mcp` / `argus-http`):

  ```bash
  pip install argus-netbox
  argus-http        # FastAPI server on :8080   ·   argus-mcp = MCP over stdio
  ```

## Integrations

Argus is the **inbound** source-of-truth layer; outbound automation consumes NetBox:

- **Ansible** ([`ansible/`](ansible/README.md)) — read-only `nb_inventory` dynamic inventory
  sourced from the NetBox Argus keeps current; target hosts by site/role with no
  hand-maintained inventory. See [ADR-0004](docs/architecture/adr/0004-netbox-ansible-inventory.md)
  for how Argus, Ansible, and (future) Terraform share NetBox without fighting over it.

## Contributing

This is a personal project run with the discipline of a shared one: changes land via
**signed-commit pull requests** with a CHANGELOG entry, decisions are captured as
**ADRs**, and work is tracked in **issues**. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache-2.0](LICENSE).
