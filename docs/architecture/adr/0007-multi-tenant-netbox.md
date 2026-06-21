# ADR-0007: Multi-Tenant NetBox — Per-Tenant Instance vs Shared + RBAC

- **Status:** Accepted (directional). Argus is single-tenant today; this records how
  multi-customer data maps to NetBox before any multi-tenant work lands.
- **Date:** 2026-06-21
- **Deciders:** Jon Freed
- **Affected:** `argus/config.py` (`NETBOX_URL`/`NETBOX_TOKEN`, future `NETBOX_TENANT`),
  `reconcile/engine.py`, deployment
- **Related:** [ADR-0001](0001-netbox-as-source-of-truth.md) (NetBox as the SoT)

## Context

Argus reconciles discovered state into NetBox, the source of truth. Managing **multiple
customers** (MSP context) needs per-customer separation. But the **community NetBox edition
(including 4.6) has _Tenancy_, not multi-tenancy**: a `Tenant` is an *ownership label* on
objects, on one shared database/UI where every user can see every tenant's data by default.
Real isolation requires **separate instances**; even filtering by tenant is leaky — IPs/prefixes
link to a tenant directly, but cables and many components resolve to one only indirectly (or not
at all). True single-instance multi-tenancy is **not on the NetBox roadmap** (verified against
4.6 release notes + community discussions).

## Decision

1. **A tenant is a self-contained stack; one NetBox instance = one tenant boundary.** Each
   customer gets its **own NetBox _and related services_** — Argus (server + discovery scope) and
   any edge/remote-access tier — deployed as a unit, sharing nothing across tenants. Argus's unit
   of multi-tenancy is the Argus⇄NetBox pairing (its own `NETBOX_URL` / `NETBOX_TOKEN`); multiple
   customers = multiple stacks. This is the default and the **recommended** mode wherever
   isolation matters.
2. **Shared-instance mode is supported as _soft_ isolation** for a single trusted operator
   running all customers on one NetBox: customers are NetBox Tenants, RBAC permission
   **constraints** (e.g. `{"tenant": <id>}`) scope views, and Argus **stamps the `tenant` field**
   on reconciled objects (optional `NETBOX_TENANT`, follow-up #86). Soft only — the
   cable/indirect-relation gaps mean it is not true isolation.

## Rationale

- Community NetBox can't isolate within one instance; Argus shouldn't pretend to. Making the
  *instance* the boundary prevents cross-customer data bleed **by construction** and keeps the
  reconcile engine simple — no cross-tenant logic or per-write tenant scoping in the hot path.
- Per-tenant instances fit Argus's existing single-SoT config and per-host deploy model
  (Ansible/compose) — a new tenant is just another deploy.

## Consequences

- Argus stays **single-`NETBOX_URL` per config**; multi-tenant (isolated) = N deploys, **no
  engine change**.
- Shared mode adds optional tenant-stamping (#86) and must document the leakiness; default
  (unset) stays single-tenant and unchanged.
- Discovery scope is per-tenant — don't mix collectors from different customers in one config.
- A tenant **stack** is provisioned as a unit (a templated deploy per customer); any cross-tenant
  rollup happens *above* the tenants, never inside a tenant's NetBox.
- Operationally heavier (N instances) for the isolated mode — accepted as the cost of real
  isolation given NetBox's limits.

## Alternatives Considered

- **One Argus/NetBox instance with internal namespacing across customers.** Rejected — community
  NetBox offers no app-level isolation; emulating it in Argus is fragile and unsafe across
  untrusted boundaries.
- **Wait for NetBox true multi-tenancy.** Rejected — not on the public roadmap.
- **Shared (Tenancy + RBAC) as the default.** Rejected as default — soft isolation with known
  leaks; offered as an opt-in mode, not the recommendation for untrusted boundaries.

## References

- NetBox Tenancy docs; "Multi-Tenant support for authorization" (community Discussion #13774);
  NetBox v4.6 release notes (no isolation feature).
- [ADR-0001](0001-netbox-as-source-of-truth.md). Follow-up: #86 (`NETBOX_TENANT` stamping).
