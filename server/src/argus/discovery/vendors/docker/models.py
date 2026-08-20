"""Docker pack value mapping — host inventory parsing and status normalization."""

from __future__ import annotations

from dataclasses import dataclass

#: NetBox manufacturer for the runtime itself. Docker hosts are real machines already
#: modelled by other packs (or by hand), so this pack never creates devices; the value
#: exists to satisfy the VendorPack descriptor.
MANUFACTURER = "Docker"

#: Docker's container states mapped onto NetBox virtual-machine status tokens.
#: ``exited`` is *offline*, not decommissioning: a stopped container is still part of the
#: stack's definition and returns on the next ``up``. An unknown state maps to offline
#: rather than active, so a state Docker adds later is never reported as healthy.
_STATUS_BY_STATE: dict[str, str] = {
    "running": "active",
    "restarting": "active",
    "created": "offline",
    "exited": "offline",
    "paused": "offline",
    "dead": "offline",
    "removing": "offline",
}

#: Compose label carrying the stack name. Containers started with plain ``docker run``
#: (buildx builders, one-off tools) have no such label.
COMPOSE_PROJECT_LABEL = "com.docker.compose.project"

#: Stack name used for containers with no compose project. Named rather than skipped:
#: they are really running, and dropping them would make NetBox claim a host runs less
#: than it does.
UNSTACKED = "unstacked"


def status_from_state(state: str | None) -> str:
    """Map a Docker container state onto a NetBox VM status token."""
    return _STATUS_BY_STATE.get((state or "").strip().lower(), "offline")


def cluster_name(host: str, project: str | None) -> str:
    """Qualify a stack name by host.

    Compose project names are unique only within a host: two machines each running a
    ``media`` stack are two clusters, not one. Qualifying at normalization time keeps that
    out of the reconcile engine, which then only ever compares names.
    """
    return f"{host}/{project or UNSTACKED}"


@dataclass(frozen=True)
class DockerHost:
    """One host the collector reads containers from."""

    name: str  # NetBox device name, and the cluster-group name
    target: str  # SSH destination, or "local" to run without SSH
    binary: str = "docker"

    @property
    def is_local(self) -> bool:
        return self.target.strip().lower() in {"local", "localhost", ""}


def parse_hosts(spec: str, binaries: str = "") -> list[DockerHost]:
    """Parse ``DOCKER_HOSTS`` (and ``DOCKER_BINARIES``) into a host list.

    ``DOCKER_HOSTS`` is ``name=target`` pairs, comma-separated::

        cerebrum=cerebrum,thor=thor,helios=root@100.119.211.234,spark=local

    ``target`` is whatever SSH takes (an alias or ``user@host``); ``local`` runs the
    command without SSH, for the host Argus itself is on.

    ``DOCKER_BINARIES`` overrides the ``docker`` path per host, same shape::

        thor=/share/ZFS530_DATA/.qpkg/container-station/bin/docker

    Kept as two flat vars rather than one nested value because a Docker path contains
    characters (``/``, ``:``) that any single-field encoding would have to escape.
    Malformed entries are skipped rather than raising: one typo in a fleet-wide list
    should not take discovery down for every other host.
    """
    overrides: dict[str, str] = {}
    for entry in (binaries or "").split(","):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        name, _, path = entry.partition("=")
        if name.strip() and path.strip():
            overrides[name.strip()] = path.strip()

    hosts: list[DockerHost] = []
    seen: set[str] = set()
    for entry in (spec or "").split(","):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        name, _, target = entry.partition("=")
        name, target = name.strip(), target.strip()
        if not name or not target or name in seen:
            continue
        seen.add(name)
        hosts.append(DockerHost(name=name, target=target, binary=overrides.get(name, "docker")))
    return hosts
