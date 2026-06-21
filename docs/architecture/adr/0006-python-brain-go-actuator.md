# ADR-0006: Python Brain, Optional Go Actuator — the Device-Action Boundary

- **Status:** Accepted (anticipatory). Network write-back is **not yet implemented** — Argus is
  read-only against the network today (writes only to NetBox). This records the language/runtime
  boundary *before* the first device action lands, so logic and the safety model don't sprawl.
- **Date:** 2026-06-21
- **Deciders:** Jon Freed
- **Affected:** future device-action layer (write-back methods on vendor packs and/or an
  `argus/actions/` surface) + an optional Go executor service; relates to `reconcile/engine.py`,
  `confirmations.py`, `discovery/vendors/`.
- **Related:** [ADR-0003](0003-discovery-reconciliation-model.md) (dry-run + confirmation-gating),
  [ADR-0005](0005-vendor-packs.md) (vendor packs / host-plugin).

## Context

Read-only-against-the-network is Argus's *current-phase* stance, not a permanent constraint
(see ROADMAP "Beyond — active management"). The next direction is **active device management**:
firmware push, config push, and similar write-backs.

These actions come in two distinct shapes:

1. **Processing before acting** — discover → normalize → diff vs NetBox → build a plan → apply
   policy/best-practices → decide *which* devices need *what* → gate it. Branching,
   transformation, decisions.
2. **Execution** — either a single controller API call, or a flat, checked, step-by-step
   runbook against a device (connect → read current version → stage image → verify checksum →
   set boot → reload → reconfirm → report).

They also vary by **transport**: cloud controllers (UniFi / Aruba Central / Mist / Meraki) are
usually *one API call*; classic gear (SSH / NETCONF / gNOI) is a *multi-step runbook*; and
fleet-scale fan-out or edge/remote execution add distribution and concurrency concerns. We need
a clear boundary before the first write-back so the safety model stays centralized.

## Decision

1. **Python is the brain.** All "process before acting" stays in Python, in-process with Argus:
   discovery/normalize/diff/plan, policy and best-practices, the **decision to act** and which
   targets, and **confirmation-gating** (dry-run by default + token, per ADR-0003). The SoT and
   the agent/MCP surface stay Python.
2. **Default executor is also Python.** A device action that is a single controller/API call
   (e.g. a cloud "upgrade device" endpoint) is implemented as a **confirmation-gated write-back
   method on the relevant `VendorPack`** — no second language for a one-liner.
3. **Go is the optional actuator tier.** Introduce a separate **Go executor** only when an action
   becomes a standalone execution concern — when one or more triggers holds:
   - a multi-step device runbook (classic SSH/NETCONF, gNOI OS-install) that is "flat steps +
     checks";
   - fleet-scale concurrent fan-out;
   - an edge/remote executor distributed as a static binary (no Python runtime on site);
   - a long-lived daemon with tight latency/resource constraints; or
   - targeting the gNOI/gNMI ecosystem (Go-native).
4. **Boundary contract.** When a Go actuator is used, Argus (Python) decides and **approves**
   work; the actuator executes **already-resolved, already-gated jobs** behind a defined interface
   (gRPC or a job protocol). The actuator holds **no policy** and makes **no decisions** — it runs
   flat, idempotent, checked runbooks and returns structured results. Each step verifies pre/post
   state (current vs target firmware, checksum, post-reboot version).
5. **Gating never moves.** Every network write — Python method or Go job — is dry-run +
   confirmation-gated like reconcile (ADR-0003). The decision-to-act stays in the brain.

## Rationale

- Matches the workflow shape: processing/branching → Python; flat checked sequences → Go. This is
  the proven control-plane / data-plane (orchestrator / worker) split.
- Keeps the safety model **centralized and auditable** — one gate in the SoT brain, not
  duplicated across languages or pushed into a worker.
- Avoids the second-language tax until it pays for itself. A one-call cloud action does not
  justify a Go binary; distribution / fan-out / gNOI do.
- Go's strengths (static binary, goroutine fan-out, gNOI/gNMI) line up exactly with the
  executor-tier triggers.

## Consequences

- Most early write-backs land as **Python pack methods**; no Go is needed yet (this ADR is
  anticipatory — network actions are still read-only / unbuilt).
- The vendor-pack SPI (ADR-0005) stays Python. A Go actuator is a *different layer* (execution
  backend), **not** a vendor pack; a pack may *delegate* a multi-step action to the actuator via
  the job interface.
- When the first Go actuator appears we commit to a defined job interface (likely gRPC); jobs must
  be fully resolved and carry an approval/confirmation token so the actuator never re-decides.
- Two toolchains / CI lanes once Go lands — accepted as the cost of the executor tier, deferred
  until a trigger fires.
- **Failure mode to guard:** decision logic creeping into the Go runner. Keep runners flat; when a
  step needs to *process*, push that decision back to Python and hand Go a resolved job.

## Alternatives Considered

- **All-Python, including a heavy executor.** Fine until edge distribution / fleet fan-out /
  gNOI — then Python's deployment and concurrency story is weaker. Kept as the *default* until a
  trigger fires.
- **Go for all device actions (incl. one-call cloud pushes).** Rejected — adds a language
  boundary and re-implements gating for what is a single HTTP call; loses cohesion with the
  Python SoT.
- **A "smart" actuator that decides.** Rejected — splits/duplicates the safety model and policy;
  the SoT brain must own the decision-to-act.
- **Embedding Go via cgo / shared library.** Rejected — a clean process/RPC boundary is simpler
  and matches the host/plugin instinct.

## References

- [ADR-0003](0003-discovery-reconciliation-model.md) — dry-run + confirmation-gated reconcile.
- [ADR-0005](0005-vendor-packs.md) — vendor packs / host-plugin boundary.
- [ROADMAP.md](../../ROADMAP.md) — "Beyond — active management (write-back)".
- gNOI / gNMI — Go-native device OS-install + streaming-telemetry ecosystem.
