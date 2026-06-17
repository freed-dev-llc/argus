# ADR-0001: NetBox as the Source of Truth; Argus as Reconciler

- **Status:** Accepted
- **Date:** 2026-06-17
- **Deciders:** Jon Freed
- **Affected:** the entire project — `server/src/argus/netbox/`, `discovery/`, `reconcile/`
- **Related:** [ADR-0003](0003-discovery-reconciliation-model.md), [docs/ARCHITECTURE.md](../../ARCHITECTURE.md)

## Context

A home/lab network's "truth" tends to scatter across device configs, a UniFi
controller, DHCP leases, spreadsheets, and memory. The goal of this project is a single
authoritative model of the network that is *always current* and that coding agents can
both read and safely update.

[NetBox](https://netbox.dev) is the de-facto open-source SoT for network infrastructure
(DCIM + IPAM): mature data model, strong REST API, a typed Python client (`pynetbox`),
and webhooks. The open question is the *relationship* between NetBox and Argus.

## Decision

**NetBox is the single source of truth. Argus is a reconciler, not a competing
datastore.** Argus observes the live network (read-only), diffs the observation against
NetBox, and updates NetBox to match. Argus stores no authoritative network state of its
own.

## Rationale

- One authoritative model avoids the "which copy is right?" problem entirely.
- NetBox already has the data model, API, and ecosystem; re-implementing it would be
  wasted effort and a second source of drift.
- A reconciler is a well-understood pattern (cf. Kubernetes controllers): observe →
  diff → converge. It maps cleanly onto "keep NetBox reflecting reality."

## Consequences

- Argus requires a reachable NetBox and an API token (`NETBOX_URL` / `NETBOX_TOKEN`).
- All Argus writes target NetBox; the network devices themselves are only ever *read*.
- Argus is useful even before reconciliation exists: the read tools turn NetBox into an
  agent-queryable surface immediately.
- Standing up NetBox itself is out of scope for Argus (a later compose profile may
  bundle it for convenience).

## Alternatives Considered

- **Argus owns its own DB and treats NetBox as one of many sinks.** Rejected — creates a
  second source of truth and the exact drift problem we're solving.
- **Build on a different SoT (NetBox alternatives / custom).** Rejected — NetBox's data
  model and ecosystem are the reason this project is tractable.

## References

- NetBox: https://netbox.dev
- pynetbox: https://github.com/netbox-community/pynetbox
