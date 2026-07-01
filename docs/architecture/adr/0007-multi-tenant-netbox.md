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

## Implementation note (#86)

`NETBOX_TENANT` landed as **create-only** stamping in the NetBox client (`netbox/client.py`):
when set, the confirmation-gated reconcile find-or-creates the tenant (`ensure_tenant`) and
`setdefault`s it onto the create payloads for **devices** (`create_device`), **IP addresses**
(`ensure_ip_address`, plus the management IP created inside `assign_primary_ip`), and the **sites**
Argus auto-creates (`ensure_site`). Stamping lives entirely in the client (a `_stamp_tenant` /
`_tenant_id` helper pair, resolved once per client instance); the reconcile engine and
`COMPARE_FIELDS` are untouched, so `tenant` is never drift-compared and an existing object's tenant
is never read or rewritten by the diff. Unset (default) is byte-for-byte the prior single-tenant
behavior.

`update_device` additionally **backfills** the tenant onto a pre-existing, untenanted device: when
a reconcile update is already writing some other drifted field (`primary_ip`/`site`/`role`/
`device_type`/`status`/`serial`), and the fetched record's `tenant` is currently unset, the
resolved tenant id is piggybacked onto that same write via `_stamp_tenant`. It never triggers a
write purely to add a tenant (tenant stays outside `COMPARE_FIELDS`), and an already-tenanted
device — any tenant, not just the configured one — is never modified on that field.

Deferred / out of scope — the known leakiness this ADR's Context warns about:

- **Prefixes** — Argus only *reads* prefixes (no `create_prefix`/`ensure_prefix` path, and the
  engine never proposes a prefix change), so they cannot be stamped without building prefix
  creation. Deferred.
- **Shared / indirect objects** — manufacturers, device types, and device roles are a shared
  catalog (no tenant); interfaces and other components, and cables, carry no tenant. These gaps
  mean shared mode stays a label, not true isolation.

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
