# ADR-0009: Vendor-Pack Practices SPI — Advisory Best-Practice Rules

- **Status:** Accepted; the `practices` extension point reserved in ADR-0005 is now defined,
  with UniFi shipping the in-tree reference rules.
- **Date:** 2026-06-24
- **Deciders:** Jon Freed
- **Affected:** `server/src/argus/discovery/practices.py` (new), `discovery/vendors/pack.py`,
  `discovery/vendors/unifi/practices.py` (new), `tools/practices_tools.py` (new),
  `server.py` + `http_server.py` (tool/endpoint registration)
- **Related:** [ADR-0005](0005-vendor-packs.md) (vendor packs),
  [ADR-0003](0003-discovery-reconciliation-model.md) (discovery + reconcile)

## Context

ADR-0005 bundled per-vendor knowledge into a `VendorPack` and **reserved** a `practices`
field (`tuple[object, ...]`, empty) as "the best-practice/validation extension point",
explicitly deferring its scope to a follow-up. Nothing in the codebase consumes the field
today — there is no validation/practices/rules framework at all.

Vendor packs need a place to encode best-practice and validation knowledge: naming
conventions, that every device resolves to a NetBox role/device-type, recommended modeling,
and similar checks. The companion `argus-vendor-packs` backlog has per-vendor
"best practices" facets (Aruba, Mist) that are **blocked** until this SPI exists.

The open question (decided below) was *what such a rule evaluates against*: the live
observation, the NetBox source of truth, or both.

## Decision

Define a small, read-only **practices SPI** in `argus.discovery.practices`:

1. **`Practice`** — a `@runtime_checkable` `Protocol`: a self-describing rule with a stable
   `id`, human `title`, default `severity`, and `evaluate(context) -> list[Finding]`.
   Structural typing means external packs need not subclass anything.
2. **`PracticeContext`** carries **both** halves of the picture: the live `observed`
   `DiscoveryResult` **and** a read-only NetBox snapshot (`netbox_devices` +
   `netbox_available`, the latter so a rule can stay silent rather than emit false findings
   when NetBox is unconfigured). The context is the extension point for additional snapshots
   later.
3. **`Finding`** — `practice` (id), `severity` (`info` / `warning` / `error`), `message`,
   optional `target` (e.g. a device name) and `remediation`.
4. **`VendorPack.practices`** is retyped from `tuple[object, ...]` to `tuple[Practice, ...]`
   (still defaulting to empty — backward compatible).
5. **`evaluate_practices(collector)`** tool (MCP tool + HTTP `GET /api/practices`): runs the
   pack's collector, builds the context (with a NetBox snapshot when configured), runs each
   declared practice, and returns findings plus a by-severity summary.
6. **UniFi ships the reference practices** (`discovery/vendors/unifi/practices.py`):
   `unifi.device-has-role` (observed-only) and `unifi.device-in-netbox` (uses both observed
   and NetBox), locking the pattern for external packs to copy.

Practices are **advisory and read-only**. They never mutate anything; acting on a finding is
a separate, confirmation-gated reconcile step (ADR-0003 stays the only writer).

## Rationale

- **Protocol over base class** keeps the public SPI loosely coupled — external packs depend
  only on `argus-netbox`, no inheritance required, mirroring how `Collector` is consumed.
- **Both-state context** lets a rule validate the live network *and* how it's modeled in
  NetBox — the two questions packs actually want to ask — without forcing every rule to open
  a NetBox client itself.
- **Self-describing rules** (`id`/`title`/`severity`) make the findings tool-, filter-, and
  UI-friendly without a heavier rules engine.
- **Read-only/advisory** preserves Argus's single-writer invariant: only the
  confirmation-gated reconcile engine writes to the source of truth.

## Consequences

- The per-vendor "best practices" facets in `argus-vendor-packs` (Aruba #5, Mist #8) are
  unblocked: a pack ships a `practices.py` and lists the rules on its `VendorPack`.
- `VendorPack.practices` is tightened to `tuple[Practice, ...]`; existing packs that don't
  set it are unaffected (empty default).
- A new advisory surface exists (`evaluate_practices` / `/api/practices`) separate from
  discovery and reconcile.
- **Follow-ups:** generic cross-pack practices (apply to every pack), surfacing findings in
  the web UI and the scheduler, and richer context snapshots (IPs, prefixes) as rules need
  them.

## Alternatives Considered

- **Plain callable `(context) -> findings`.** Rejected — not self-describing (no stable id /
  severity / title for tooling and filtering).
- **Evaluate observed-only, or NetBox-only.** Rejected — observed-only can't flag modeling
  drift; NetBox-only can't flag live issues. The context carries both (the chosen option).
- **A full rules/policy engine or an external linter.** Rejected — overkill for advisory
  per-vendor checks; a tiny Protocol is enough and stays in the SPI.
- **Persist findings into NetBox.** Rejected for v1 — practices are advisory; persisting
  would blur the single-writer (reconcile) boundary.

## References

- [ADR-0005](0005-vendor-packs.md) — vendor packs (reserved the `practices` field).
- [ADR-0003](0003-discovery-reconciliation-model.md) — discovery + confirmation-gated reconcile.
- Companion decision issue: `freed-dev-llc/argus-vendor-packs#18`.
