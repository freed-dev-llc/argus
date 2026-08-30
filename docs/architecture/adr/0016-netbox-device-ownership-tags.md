# ADR-0016: Scope NetBox Device Ownership with Tags

- **Status:** Accepted
- **Date:** 2026-08-30
- **Deciders:** Jon Freed
- **Affected:** device reconciliation, manually declared off-LAN devices
- **Related:** [ADR-0001](0001-netbox-as-source-of-truth.md), [ADR-0004](0004-netbox-ansible-inventory.md)

## Context

ADR-0004 requires ownership to be scoped before a writer other than Argus creates
intent objects in NetBox. Argus also reports every NetBox-only device as unseen. That
is useful for discovered infrastructure, but creates permanent noise for off-LAN
devices that a LAN collector cannot observe.

## Decision

Device ownership is marked with NetBox tags:

- `argus-discovered`: Argus owns fields learned through discovery and reconciliation.
- `argus-intent`: a human or intent-management tool owns the device. Argus does not
  update it and does not include it in collector-specific stale-device notes.

Argus stamps `argus-discovered` on every device it creates. Untagged existing devices
remain treated as discovered for backward compatibility; this avoids silently
abandoning the fleet already managed before ownership tags existed. Operators may
migrate those records to `argus-discovered` over time.

Collectors that need a narrower stale boundary may add a source tag alongside
`argus-discovered`. NetBird uses `argus-source-netbird`, so its stale report considers
only devices explicitly assigned to that source.

If a collector observes a device tagged `argus-intent`, Argus reports the ownership
collision as a note and performs no write. The tag therefore governs ownership, not
reachability: adding NetBird discovery later does not silently transfer an intent
device to Argus.

## Consequences

- Off-LAN VPSes may be entered in NetBox with `argus-intent` without producing stale
  LAN-discovery noise.
- A future second writer may only manage `argus-intent` devices.
- Transferring ownership requires an explicit tag change.
- Tags scope device records only. Ownership for IP addresses and workload objects must
  be decided separately before a second writer manages those object types.

## Alternatives Considered

- **A generic `intent` tag.** Rejected because its ownership semantics are ambiguous
  outside Argus.
- **Treat all untagged devices as intent.** Rejected because it would stop management
  of the existing discovered fleet immediately.
- **Filter stale notes by site.** Rejected because site describes location, not writer
  ownership, and would not prevent updates when names collide.
