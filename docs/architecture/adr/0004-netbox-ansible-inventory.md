# ADR-0004: NetBox as the Inventory Hub for Ansible (and the Two-Writers Rule)

- **Status:** Accepted
- **Date:** 2026-06-17
- **Deciders:** Jon Freed
- **Affected:** `ansible/`, the relationship between Argus and the terraform/ansible automation repos
- **Related:** [ADR-0001](0001-netbox-as-source-of-truth.md), [ADR-0003](0003-discovery-reconciliation-model.md)

## Context

Argus keeps NetBox reflecting the *actual* network (inbound discovery → reconcile). The
natural complement is *outbound* automation: Ansible/Terraform acting on that truth. The
existing automation repos (`terraform-provider-turingpi`, `turing-ansible-cluster`, …) are
push-based IaC (intended state → hardware); their structural gap is a trustworthy
"what's actually out there now?" — which is exactly what Argus + NetBox provide.

The question: how should Ansible (and later Terraform) relate to the NetBox that Argus owns?

## Decision

1. **NetBox is the hub.** Argus is the inbound discovery/source-of-truth layer; Ansible and
   Terraform are outbound consumers/pushers. They pivot on NetBox, not on each other.
2. **Start with read-only Ansible dynamic inventory** (`netbox.netbox.nb_inventory`, under
   `ansible/`). It reads NetBox to build inventory grouped by site/role/etc. Being read-only,
   it cannot conflict with Argus.
3. **Two-writers rule:** if a tool ever *writes* to NetBox alongside Argus (e.g.,
   `terraform-provider-netbox` managing *intent* objects), ownership must be scoped first —
   Argus owns **discovered** objects (tagged/marked as such), the other tool owns **intent**
   objects — so neither clobbers the other. That scoping gets its own ADR before any second
   writer lands.

## Rationale

- Dynamic inventory from the SoT is the canonical, low-risk, high-value integration: zero
  write conflict, and inventory is always current because Argus keeps NetBox current.
- Keeping MCP (interactive/agent) and IaC (deterministic CI/CD) as different *modes* over the
  same SoT lets them coexist without overlap.

## Consequences

- `ansible/` ships an `nb_inventory` config + demo playbook; consuming it needs the
  `netbox.netbox` collection + `pynetbox` on the control node.
- No `terraform-provider-argus` — NetBox already has a mature provider; Argus's value is the
  reconcile *loop*, not declarative resources.
- A future scheduled-drift action (ROADMAP P4) must not auto-trigger config pushes without an
  explicit gate, so a discovery glitch can never push bad config.

## Alternatives Considered

- **Hand-maintained Ansible inventory.** Rejected — drifts from reality; defeats the SoT.
- **Let Terraform and Argus both write NetBox freely.** Rejected — guarantees drift wars
  (each undoes the other). Ownership must be scoped first.

## References

- `netbox.netbox` collection / `nb_inventory` plugin.
- `ansible/README.md`.
