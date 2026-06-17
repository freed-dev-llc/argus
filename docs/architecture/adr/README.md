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

## Adding a new ADR

1. Pick the next sequential number.
2. Copy the format from any existing ADR.
3. Update this index.
4. Cross-reference the ADR from the relevant doc (e.g., `docs/ARCHITECTURE.md`).
