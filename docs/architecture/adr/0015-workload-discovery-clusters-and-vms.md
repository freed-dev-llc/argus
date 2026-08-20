# ADR-0015: Workload Discovery — Clusters and Virtual Machines

- **Status:** Accepted; the Docker pack is the first in-tree workload pack (this change).
- **Date:** 2026-08-20
- **Deciders:** Jon Freed
- **Affected:** `server/src/argus/discovery/base.py`, `discovery/vendors/docker/`,
  `netbox/client.py`, `reconcile/engine.py`
- **Related:** [ADR-0003](0003-discovery-reconciliation-model.md) (discovery/reconcile model),
  [ADR-0005](0005-vendor-packs.md) (vendor packs),
  [ADR-0010](0010-management-plane-contract.md) (observed values are mapped at observe time)

## Context

Argus models the network plane: devices, IPs, prefixes, cabling, topology. That answers
"what is on the network" but not "what is running on it". The gap became concrete while
onboarding a fleet into NetBox so [helios](https://github.com/freed-dev-llc/helios) could
federate it (helios ADR-0002, *"if it's not in the CMDB, it isn't monitored"*): the hosts
were absent, and so were the ~100 containers across ~30 Compose stacks they run.

Seeding that by hand re-creates exactly the drift Argus exists to remove. Containers churn
harder than switches do: CI runners come and go, a media stack gets rebuilt, a service
moves hosts. A hand-entered container inventory is stale within a day.

`DiscoveryResult` had nowhere to put any of it. It carries devices, clients, links, and
IPs, all of which map to DCIM/IPAM. NetBox's virtualization objects (cluster types,
cluster groups, clusters, virtual machines) had no representation on either side of the
diff.

## Decision

**Extend the discovery contract with a workload plane, and reconcile it through the same
confirmation-gated engine as everything else.**

Two new normalized types on `DiscoveryResult`:

- `DiscoveredCluster` — a grouping of workloads on one host. A Compose stack is the
  motivating case.
- `DiscoveredVM` — a workload inside a cluster. A container, or a real VM if a future pack
  reports one.

They map onto NetBox as:

```
ClusterType     "Docker"
ClusterGroup    one per host           cerebrum
Cluster         one per host + stack   cerebrum/infra
VirtualMachine  one per container      aria-prometheus
```

Three properties of that mapping are deliberate:

**Cluster names are qualified by host.** Compose project names are unique only within a
host: two machines each running a stack called `media` are two clusters, not one.
Qualification happens at normalization time, so the reconcile engine only ever compares
names.

**The host association lives on the cluster group, not on the cluster.** NetBox's
`Device.cluster` is single-valued, so a host running several stacks cannot point them all
at itself. A group per host expresses the real relationship without fighting the schema.

**A workload pack reports no devices.** The Docker pack contributes clusters and VMs only.
The hosts are real machines that the network packs (or a human) already model, and a
container runtime is a poor authority on the identity of the metal underneath it. A host
absent from NetBox therefore surfaces as an unresolved reference rather than a
half-invented device.

The first pack is `docker`, on a new `Transport.HOST_SSH`: there is no controller to ask,
so acquisition is per host over SSH, reading `docker ps -a`. It is read-only against the
runtime; the only writes Argus makes are into NetBox.

## Rationale

- **Same engine, same gate.** Workloads diff and apply through `ReconcileEngine`, so they
  inherit dry-run-by-default, per-change results, and the never-auto-delete posture. No
  second write path to audit.
- **Additive for every existing pack.** The new fields default to empty, and the workload
  diff returns immediately when a result carries none. UniFi, firewall, SNMP, and DHCP/ARP
  behave exactly as before.
- **Status is mapped at observe time**, following ADR-0010: the pack turns Docker's state
  vocabulary into a NetBox status token, and the raw value stays on `.raw`. An unrecognized
  state maps to `offline` rather than `active`, so a state Docker adds later is never
  reported as healthy.

## Consequences

- **Unreachable is not empty.** This is the property that makes the pack safe to schedule.
  A host whose SSH fails is recorded in `unreachable_hosts` and its clusters are excluded
  from the comparison, because "unknown" must never diff as "empty" and propose retiring a
  stack on a transient outage. A host with no Docker installed is different: that is a real
  zero, is noted as such, and reconciles down normally. Distinguishing them took a real
  bug to notice, and the distinction is now covered by tests.
- **Workload identity is (cluster, name), not name.** Container names are unique per
  cluster, not globally: a fleet routinely runs `watchtower` on several hosts. NetBox scopes
  VM names the same way. Keying on the name alone collides those into one record and reports
  a cluster drift that flip-flops on every run, which is exactly what the first live run
  produced (`watchtower` plus three `n8n-*` containers across two hosts). The cost of the
  correct key is that a container moved between stacks on one host reads as a create plus a
  note about the record left behind, rather than an update. That is the honest report, and
  moves are rarer than name collisions.
- **NetBox-only workloads are reported, never auto-deleted**, matching the device posture,
  and the staleness report is scoped to clusters the run actually observed.
- **Hosts must be reachable from wherever the collector runs**, with key-based SSH. The
  collector uses `BatchMode=yes` so a missing key fails fast instead of hanging discovery
  on a password prompt. A containerized Argus needs the key mounted and the hosts in
  `known_hosts`.
- **Per-host binary overrides are needed in practice.** QNAP's Container Station keeps
  `docker` off `PATH`, so `DOCKER_BINARIES` exists alongside `DOCKER_HOSTS`. Two flat vars
  rather than one nested value, because a Docker path contains characters any single-field
  encoding would have to escape.
- Cluster/VM deletion is out of scope, as device deletion is. Retiring a workload stays a
  human decision.

## Alternatives Considered

- **NetBox services instead of virtualization objects.** Model published ports on the host
  device and skip containers entirely. Smaller and more stable, but it answers "what is
  reachable" rather than "what is running", and loses the stack grouping that makes the
  inventory navigable.
- **A cluster per host, with the stack as a VM tag or custom field.** Keeps `Device.cluster`
  usable, but buries the stack in a field that neither the UI nor the API groups by, and
  stacks are the unit people actually reason about.
- **A standalone sync script outside Argus.** Fastest to write, and a first pass was built
  that way. Rejected as the destination: it is a second, ungated write path into the source
  of truth, with its own idea of idempotency and no confirmation step, which is precisely
  what ADR-0003 centralized.
- **Docker API over TCP instead of SSH.** Needs the daemon socket exposed on every host,
  which is a far larger attack surface than an SSH key for a read-only `ps`.

## References

- NetBox virtualization model: https://netboxlabs.com/docs/netbox/models/virtualization/cluster/
- Docker `ps --format`: https://docs.docker.com/reference/cli/docker/container/ls/#format
- helios ADR-0002 (NetBox drives what is monitored):
  https://github.com/freed-dev-llc/helios/blob/main/docs/architecture/adr/0002-netbox-as-monitoring-source-of-truth.md
