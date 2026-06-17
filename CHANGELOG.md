# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

[Unreleased]: https://github.com/freed-dev-llc/argus/commits/main
