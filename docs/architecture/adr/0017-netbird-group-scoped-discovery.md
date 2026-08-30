# ADR-0017: Group-Scoped NetBird Discovery for Off-LAN Devices

- **Status:** Accepted
- **Date:** 2026-08-30
- **Deciders:** Jon Freed
- **Affected:** discovery, reconciliation, off-LAN device inventory
- **Related:** [ADR-0003](0003-discovery-reconciliation-model.md), [ADR-0016](0016-netbox-device-ownership-tags.md)

## Context

LAN discovery cannot observe cloud VPSes, while NetBird's management API already has
their stable names, mesh addresses, and connection state. Importing every NetBird peer
is unsafe: LAN hosts are also mesh peers, and an overlay address must not displace the
LAN management address learned by UniFi or another local collector.

## Decision

Argus discovers NetBird peers through the supported, read-only management REST API.
`NETBIRD_GROUP` is required and acts as the source-ownership boundary. A run imports
only peers belonging to that group; a missing or empty group produces no devices and
an explanatory note, never a fallback to all peers.

For each selected peer, NetBird owns only:

- device identity by peer name;
- the mesh address as `primary_ip`;
- mapped online/offline status;
- observational agent/version metadata retained in the discovery result.

Site, role, model, and manufacturer are unknown by default, so reconciliation leaves
those existing NetBox fields untouched. Optional `NETBIRD_SITE`, `NETBIRD_ROLE`, and
`NETBIRD_MODEL` defaults may be supplied together when the group is homogeneous and
new peers should be bootstrapped automatically.

Devices initially entered by hand remain `argus-intent` and read-only under ADR-0016.
After a successful NetBird dry run matches the expected records, ownership is
transferred explicitly by replacing `argus-intent` with both `argus-discovered` and
`argus-source-netbird`. The source tag limits NetBird stale reporting to records that
NetBird actually owns; it cannot classify LAN-discovered devices as stale.

## Consequences

- LAN and mesh discovery remain complementary instead of competing across the fleet.
- NetBird group membership is the durable inclusion control; Argus carries no host list.
- `argus-source-netbird` is the reconciliation boundary for NetBird-owned records.
- A NetBird API personal access token is required and stored only in the deployment's
  gitignored environment file.
- Group membership changes can add or remove objects from a run, but stale objects are
  only reported and never deleted.

## Alternatives Considered

- **Read NetBird's SQLite store.** Rejected because its schema is an internal
  implementation detail and requires filesystem access to the management host.
- **Import all peers.** Rejected because mesh and LAN collectors would fight over primary
  IPs for hosts present in both sources.
- **Maintain an Argus peer-name allowlist.** Rejected because it creates another inventory
  source of truth; NetBird groups already express the boundary.
