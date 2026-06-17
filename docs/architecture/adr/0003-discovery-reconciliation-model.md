# ADR-0003: Pluggable Discovery + Dry-Run, Confirmation-Gated Reconciliation

- **Status:** Accepted; UniFi discovery (#7), reconcile `diff` + confirmation-gated `apply`
  (#10), and NetBox write FK-resolution (#29) implemented 2026-06-17. `apply` may create
  supporting objects (site/role/manufacturer/device-type) and assigns primary IPs via IPAM
  (assumes a `mgmt` interface, /32, IPv4). Remaining: SNMP/LLDP (#8) and DHCP/ARP (#9) collectors.
- **Date:** 2026-06-17
- **Deciders:** Jon Freed
- **Affected:** `server/src/argus/discovery/`, `reconcile/engine.py`, `confirmations.py`, `tools/`
- **Related:** [ADR-0001](0001-netbox-as-source-of-truth.md)

## Context

To keep NetBox reflecting reality, Argus must (1) learn the real state from many
heterogeneous sources and (2) change NetBox accordingly. Both are risky: discovery
touches many protocols, and writes mutate the source of truth — a buggy reconcile could
corrupt the very thing we trust. An agent driving these tools must not be able to make
silent, sweeping changes.

## Decision

1. **Pluggable discovery.** A `Collector` interface (`discovery/base.py`) with one method,
   `collect() -> DiscoveryResult`. Each source (UniFi, SNMP/LLDP, DHCP/ARP, …) is a
   separate collector registered in a `COLLECTORS` map and selectable by name. Collectors
   are **read-only** against the network.
2. **Normalize, then diff.** Collectors emit a common `DiscoveryResult`
   (`DiscoveredDevice`, IPs, notes). The `ReconcileEngine` diffs that against NetBox and
   produces a typed `ReconcilePlan` of `create`/`update`/`delete` changes.
3. **Dry-run by default.** `diff()` never writes. `apply()` writes only when called with
   `confirm=True`.
4. **Confirmation-gated tools.** `reconcile_apply` returns a `confirmation_required`
   token first; a second explicit call with the token performs the change (short TTL,
   `confirmations.py`). This makes destructive intent explicit and auditable.

## Rationale

- A narrow `Collector` contract lets us add sources incrementally without touching the
  engine, and lets each collector be tested in isolation.
- Normalizing before diffing keeps the engine independent of any one protocol.
- Dry-run + confirmation mirrors the safety model already proven in `aria-unifi-mcp`'s
  admin tools, and protects the SoT from agent error.

## Consequences

- Collectors and the diff/apply internals ship as **stubs** that return clear
  "not yet implemented" results, so the full path is exercisable before the hard parts land.
- Heavy discovery libraries (`napalm`, `netmiko`, `pysnmp`) live in an optional
  `discovery` extra — the base install stays light.
- Every reconcile is a two-step interaction for agents (plan, then confirm). Accepted as
  the cost of safety.

## Alternatives Considered

- **Auto-apply discovered changes.** Rejected — unacceptable risk to the SoT and removes
  the human/agent review point.
- **One monolithic discovery routine.** Rejected — untestable and couples the engine to
  every protocol.

## References

- Reconciler pattern (observe → diff → converge).
- `aria-unifi-mcp/confirmations.py` — confirmation-gating prior art.
