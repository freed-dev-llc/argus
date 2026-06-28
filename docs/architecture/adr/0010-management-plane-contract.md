# ADR-0010: Management-Plane → NetBox Contract for Vendor Packs

- **Status:** Accepted; the read-only contract (a typed `management` object on discovered
  devices) ships now, with UniFi as the worked example. Write-back is a defined, gated
  follow-up phase.
- **Date:** 2026-06-24
- **Deciders:** Jon Freed
- **Affected:** `server/src/argus/discovery/base.py` (`DeviceManagement` + a `management`
  field), `discovery/vendors/unifi/collector.py` (worked example); `reconcile/engine.py`
  (write-back, future)
- **Related:** [ADR-0003](0003-discovery-reconciliation-model.md) (reconcile),
  [ADR-0005](0005-vendor-packs.md) (vendor packs), [ADR-0009](0009-vendor-pack-practices-spi.md)

## Context

The per-vendor "management" facets in `argus-vendor-packs` (Aruba #6, Mist #9) want to
surface management-plane data — operational status, firmware, serial, management IP /
interface / VLAN, controller+site association — into NetBox, **read-only first**, with active
write-back as the eventual, trust-gated direction.

Today `DiscoveredDevice` has no typed home for this; the only catch-all is `raw`. The
reconcile engine writes `name`, `primary_ip`, `site`, `role`, `model`, `manufacturer` and
diffs on `COMPARE_FIELDS = (primary_ip, site, role)`; apply is confirmation-gated
(`confirm_token`, ADR-0003). No firmware/status/management mapping exists.

## Decision

1. **Typed carrier.** Add a `DeviceManagement` dataclass (`status`, `serial`, `firmware`,
   `mgmt_ip`, `mgmt_interface`, `mgmt_vlan` — all optional) and a single additive field
   `DiscoveredDevice.management: DeviceManagement | None = None`. Nested + typed keeps it
   explicit and discoverable without bloating the device's identity fields; the `None`
   default is fully backward compatible.
2. **Read-only first (this phase).** Packs populate `management`; it is surfaced by
   `discovery_scan` (nested dataclass serialized via `asdict`) and is available to practices
   (ADR-0009). **No NetBox writes** of management data yet — the reconcile engine and its
   contract are untouched.
3. **Write-back (defined, gated, phase 2).** When discovery + practices are trusted, the
   reconcile engine maps management fields into NetBox through the **existing
   confirmation-gated flow**: `status` → device status, `serial` → device serial, `firmware`
   → a device custom field (or platform), `mgmt_ip` → `assign_primary_ip`. These become
   opt-in, per-field additions to the desired-device build and (where drift should be
   corrected) to `COMPARE_FIELDS`. No management write happens without confirmation.
4. **Worked example.** The UniFi collector populates `management` from its device payload
   (`state` → status, `version` → firmware, `serial` → serial), returning `None` when it
   learns nothing.

## Rationale

- **Nested typed object** beats flat fields (no identity bloat) and `raw` conventions (typed,
  explicit, self-documenting) while staying one additive, backward-compatible field.
- **Read-only first** matches the stated phase, immediately gives packs + practices a uniform
  management surface, and avoids destabilizing the reconcile engine (and its exact-payload
  tests) before the data is trusted.
- **Reuse the confirmation gate** for write-back keeps one consistent safety model — an agent
  still can't mutate the source of truth in a single step.

## Consequences

- The management facets (Aruba #6, Mist #9) are unblocked for their read-only phase: a pack
  fills `DiscoveredDevice.management` and the data flows through `discovery_scan` and into
  practices.
- `discovery_scan` output gains a `management` object per device (`null` when absent).
- **Follow-up (write-back):** extend `_desired_device` / `COMPARE_FIELDS`, add NetBox client
  writes for `serial` / `status` / `firmware` (incl. the custom-field modeling decision for
  firmware), all behind the existing confirmation flow — tracked as the management write-back
  task.

## Update — UniFi state→status mapping (#119, 2026-06-27)

`status` joins `serial` (#124) in the management-plane write-back (firmware/platform still
deferred): it is now in `COMPARE_FIELDS`, sourced from the nested `management` object via
`_observed_value`, and written directly (a plain CharField, no FK resolution) through the existing
confirmation-gated apply.

The UniFi pack maps its raw device `state` to a NetBox status with a **deliberately conservative
table**, kept as the single source of truth in `discovery/vendors/unifi/models.py`
(`_UNIFI_STATE_TO_NETBOX_STATUS` / `status_from_state`):

| UniFi `state` | NetBox status |
|---|---|
| `ONLINE` | `active` |
| `OFFLINE` | `offline` |
| `PENDING_ADOPTION` | `staged` |
| `ADOPTING` | `staged` |
| anything else / unknown / transient (`UPDATING`, `PROVISIONING`, `GETTING_READY`, …) / `None` / missing | *(unmapped)* → `None` |

**Safety rule — unknown → skip.** Input is matched case-insensitively (`.upper()`); any state not
in the table returns `None`. A `None` observed `status` (no `management`, or an unmapped/transient
state) hits the diff loop's `desired is None → continue` skip, so a sparse or transient discovery
run never blanks out or churns the status NetBox already holds. Transient states are intentionally
left out of the table (kept in the skip bucket) rather than mapped to `active`. Writes use the
lowercase NetBox token (`active`/`offline`/`staged`).

## Alternatives Considered

- **Flat fields on `DiscoveredDevice`** (`status`, `firmware`, …). Viable and simplest for
  the engine to map, but bloats the core identity dataclass; rejected in favour of grouping.
- **Reuse `raw` + a documented convention.** Rejected — untyped and implicit; every consumer
  re-implements key lookups.
- **Write management to NetBox immediately in reconcile.** Rejected — violates "read-only
  first" and risks churning the source of truth before the data is trusted.
- **A separate management collector/result type.** Rejected — duplicates acquisition; the
  device already is the natural carrier.

## References

- [ADR-0003](0003-discovery-reconciliation-model.md) — confirmation-gated reconcile.
- [ADR-0005](0005-vendor-packs.md) — vendor packs.
- [ADR-0009](0009-vendor-pack-practices-spi.md) — practices SPI (consumes `management`).
- Companion decision issue: `freed-dev-llc/argus-vendor-packs#19`.
