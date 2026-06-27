# ADR-0011: Webhook Reactions — Read-Side Only (Event-Triggered Drift, Never Auto-Apply)

- **Status:** Accepted — reactions implemented (#72, 2026-06-27)
- **Date:** 2026-06-27
- **Deciders:** Jon Freed
- **Affected:** `server/src/argus/webhooks.py`, `http_server.py` (`netbox_webhook` handler),
  `scheduler.py` (`run_drift_cycle` reused), `config.py` (opt-in toggle)
- **Related:** [ADR-0001](0001-netbox-as-source-of-truth.md),
  [ADR-0003](0003-discovery-reconciliation-model.md); P4 webhook classify (#46) + scheduler (#47); #72

## Context

`POST /webhooks/netbox` is observability-only today: it classifies the change event,
structured-logs it, and acks (#46). Authenticity is now enforced via HMAC verification of
`X-Hook-Signature` (#71). Issue #72 ("P4 webhook reactions") asks Argus to **react** to NetBox
events — and its wording floats "optionally a confirmation-gated reconcile."

That phrase is the decision this ADR settles. A webhook is an **externally triggerable,
machine-driven, potentially high-frequency** signal. Letting an inbound event drive a NetBox
**write** — even a confirmation-gated one — would be the first path that bypasses the human/agent
confirmation step ADR-0003 makes sacrosanct. The value of reactions (notice drift promptly when
NetBox changes) does **not** require any write to deliver.

## Decision

1. **v1 reactions are read-side only.** A relevant NetBox event triggers a **discovery + diff**
   (drift) refresh and an optional alert — and **never** an `apply` / NetBox write. The reaction
   invokes the existing read-only `scheduler.run_drift_cycle()`, so it inherits ADR-0003's
   no-write guarantee *by construction* — there is no write code on the reaction path to get wrong.
2. **No auto-apply, ever, in v1.** The confirmation-gated reconcile that #72 floats is explicitly
   **deferred** to a future, separately-decided ADR. An external event must not silently mutate the
   source of truth; if event-driven reconciliation is ever wanted it is a deliberate decision, not
   a config flag.
3. **Opt-in, safe default off.** Reactions run only when explicitly enabled (new setting; unset =
   today's classify-and-log behavior, byte-for-byte unchanged).
4. **Authentic events only.** A reaction fires only for a request that passed authentication — HMAC
   signature verified (`NETBOX_WEBHOOK_SECRET` set, #71) and/or bearer auth (`HTTP_TOKEN`). Argus
   will not run a collector off an unauthenticated/forgeable event. This ties #72 to #71: reactions
   are gated on the authenticity #71 provides.
5. **Coalesced + single-flight.** NetBox can emit bursts. Events are debounced (coalesced within a
   short window into one cycle) and at most one drift cycle runs in flight per collector, so an event
   storm can't stampede the collector or the controller.
6. **Filtered triggers.** Only a configurable set of event models triggers a cycle (default: the
   models drift actually reconciles — e.g. `dcim.device`, `ipam.ipaddress`); other events are still
   classified and logged but trigger nothing.

## Rationale

- **One mechanism, two triggers.** The interval scheduler (#47) and webhook reactions both drive
  the *same* read-only `run_drift_cycle`. Reactions are a new *trigger*, not a new write path, so the
  safety model is reused, not re-argued, and there is far less new surface to audit.
- **Authenticity precondition** makes the feature safe to enable on an internet-reachable endpoint:
  #71's HMAC is the gate, reactions are the consumer.
- **Debounce/single-flight** keeps the blast radius of a chatty NetBox bounded.

## Consequences

- Argus notices NetBox changes near-real-time (drift status + optional alert), complementing the
  fixed-interval scheduler — without crossing the SoT-write line.
- The webhook handler gains an opt-in, debounced side effect; ack semantics are unchanged.
- A future "event-driven, confirmation-gated reconcile" remains possible but requires its own ADR
  and Jon's explicit decision. This ADR deliberately closes the door on silent event-driven writes.

## Alternatives Considered

- **Event-driven auto-apply (the #72 "optional reconcile").** Rejected for v1 — bypasses ADR-0003's
  confirmation gate; an external event must never silently mutate the source of truth.
- **A separate reaction engine.** Rejected — it would duplicate the scheduler's read-only drift
  path. Reuse `run_drift_cycle` (altitude: generalize the trigger, don't fork the mechanism).
- **React to every event with no debounce.** Rejected — event storms would stampede discovery and
  the controller.
- **React without an authenticity precondition.** Rejected — a forgeable event could make Argus burn
  collector/controller cycles on demand; gate on #71's HMAC.

## References

- [ADR-0001](0001-netbox-as-source-of-truth.md), [ADR-0003](0003-discovery-reconciliation-model.md)
- `server/src/argus/scheduler.py` — `run_drift_cycle` (the read-only drift path reused as the reaction)
- #46 (classify + log), #47 (scheduler), #71 (HMAC verification), #72 (this work)
