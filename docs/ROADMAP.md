# Roadmap

Phased plan. Each phase is a set of GitHub issues; architectural choices get an ADR.

## P0 — Scaffold ✅ (this cut)

- Monorepo: Python MCP/FastAPI server + React/Vite/TS web app.
- NetBox read tools (`pynetbox`) wired through MCP + HTTP.
- Pluggable discovery + reconciliation interfaces (stubbed).
- Governance: ADRs, CHANGELOG, CI, Dependabot, issue/PR templates.

## P1 — Observe the real network

- Implement the **UniFi collector** (reuse credentials/approach from `aria-unifi-mcp`).
- Implement **SNMP/LLDP** and **DHCP/ARP** collectors for neighbor/topology and IP/MAC data.
- Normalize collector output into a shared `DiscoveryResult` shape.
- Web: device table populated from live NetBox data.

## P2 — Reconcile

- Implement `ReconcileEngine.diff()`: compare observed state vs NetBox, emit a typed plan.
- Implement `apply()` with confirmation gating and per-object create/update.
- `drift_report` returns real drift; web drift panel shows it.

## P3 — Visualize

- Topology map in the web app (evaluate `react-flow` / `cytoscape`).
- Render cabling / LLDP neighbors and IPAM hierarchy.

## P4 — Stay current automatically

- NetBox webhooks (`/webhooks/netbox`) → react to changes.
- Scheduled discovery + reconcile (dry-run) with drift alerting.

## P5 — Hardening & open source

- HTTP auth, deployment story (compose profile that bundles NetBox), container/PyPI publish.
- Docs pass, examples, and the public open-source flip.
