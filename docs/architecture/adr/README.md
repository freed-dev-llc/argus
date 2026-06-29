# Architecture Decision Records (ADRs)

Architecture decisions for Argus, recorded in the format established by the leeloo/aria
repos.

## Format

```markdown
# ADR-XXXX: Title

- **Status:** Accepted | Proposed | Deprecated | Superseded
- **Date:** YYYY-MM-DD
- **Deciders:** ...
- **Affected:** ...
- **Related:** ...

## Context
## Decision
## Rationale
## Consequences
## Alternatives Considered
## References
```

## Index

| ADR | Title | Date | Status |
|-----|-------|------|--------|
| [0001](0001-netbox-as-source-of-truth.md) | NetBox as the Source of Truth; Argus as Reconciler | 2026-06-17 | Accepted |
| [0002](0002-monorepo-python-server-react-web.md) | Monorepo: Python MCP/FastAPI Server + React/Vite/TS Web | 2026-06-17 | Accepted |
| [0003](0003-discovery-reconciliation-model.md) | Pluggable Discovery + Dry-Run, Confirmation-Gated Reconciliation | 2026-06-17 | Accepted |
| [0004](0004-netbox-ansible-inventory.md) | NetBox as the Inventory Hub for Ansible (and the Two-Writers Rule) | 2026-06-17 | Accepted |
| [0005](0005-vendor-packs.md) | Vendor Packs — a Host/Plugin Boundary for Per-Vendor Discovery | 2026-06-21 | Accepted |
| [0006](0006-python-brain-go-actuator.md) | Python Brain, Optional Go Actuator — the Device-Action Boundary | 2026-06-21 | Accepted |
| [0007](0007-multi-tenant-netbox.md) | Multi-Tenant NetBox — Per-Tenant Instance vs Shared + RBAC | 2026-06-21 | Accepted |
| [0008](0008-ask-the-brain-mnemosyne.md) | Ask the Brain — Mnemosyne Integration | 2026-06-24 | Accepted |
| [0009](0009-vendor-pack-practices-spi.md) | Vendor-Pack Practices SPI — Advisory Best-Practice Rules | 2026-06-24 | Accepted |
| [0010](0010-management-plane-contract.md) | Management-Plane → NetBox Contract for Vendor Packs | 2026-06-24 | Accepted |
| [0011](0011-webhook-reactions-read-side-only.md) | Webhook Reactions — Read-Side Only (Event-Triggered Drift, Never Auto-Apply) | 2026-06-27 | Accepted |
| [0012](0012-maintenance-mcp-surface.md) | Maintenance MCP Surface — a Separate `argus-maint` Server (Read/Preview-Only First) | 2026-06-27 | Accepted |
| [0013](0013-paired-vendor-knowledge-packs.md) | Paired Vendor + Knowledge Packs (Argus ↔ Mnemosyne) | 2026-06-29 | Accepted |

## Adding a new ADR

1. Pick the next sequential number.
2. Copy the format from any existing ADR.
3. Update this index.
4. Cross-reference the ADR from the relevant doc (e.g., `docs/ARCHITECTURE.md`).
