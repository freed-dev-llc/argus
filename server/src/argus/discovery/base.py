"""Discovery interfaces.

A :class:`Collector` observes live network state from one source and returns a
normalized :class:`DiscoveryResult`. Collectors are read-only against the network — the
only writes Argus makes are into NetBox, via the reconcile engine (see ADR-0003).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeviceManagement:
    """Management-plane facts about a device (read-only first; see ADR-0010).

    Optional, vendor-reported management metadata that doesn't fit the core identity fields.
    Surfaced by discovery today; writing it back into NetBox is the gated next phase (it
    reuses the reconcile confirmation flow, ADR-0003). All fields optional — a pack populates
    what it knows.
    """

    status: str | None = None  # operational state, e.g. "active" / "online" / "offline"
    serial: str | None = None
    firmware: str | None = None
    mgmt_ip: str | None = None  # management IP, if distinct from primary_ip
    mgmt_interface: str | None = None
    mgmt_vlan: int | None = None


@dataclass
class DiscoveredDevice:
    """A device observed on the live network, normalized across collectors."""

    name: str
    mac: str | None = None
    primary_ip: str | None = None
    site: str | None = None
    role: str | None = None
    model: str | None = None
    manufacturer: str | None = None
    management: DeviceManagement | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveredClient:
    """An endpoint/client observed on the network (the IP/MAC-binding side)."""

    mac: str | None = None
    ip: str | None = None
    hostname: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveredLink:
    """A directed link between two devices (e.g. a device and its uplink)."""

    local_device: str
    remote_device: str
    local_port: str | None = None
    remote_port: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveredCluster:
    """A grouping of workloads running on one host (ADR-0015).

    A Docker Compose project is the motivating case: ``name`` is qualified by host
    (``"cerebrum/infra"``) because stack names are only unique per host, and two hosts
    running a stack called ``media`` are two different clusters.

    ``host`` names the device this cluster runs on. It maps to a NetBox *cluster group*
    rather than ``Cluster.scope``, because a host runs several stacks while
    ``Device.cluster`` is single-valued: pointing every stack's cluster at the same device
    is not expressible in NetBox.
    """

    name: str
    host: str | None = None
    cluster_type: str = "Docker"
    status: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveredVM:
    """A workload inside a cluster — a container, or a real VM (ADR-0015)."""

    name: str
    cluster: str  # matches a DiscoveredCluster.name in the same result
    status: str | None = None  # already a NetBox status token; the pack maps it
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryResult:
    """The normalized output of a single collector run."""

    collector: str
    devices: list[DiscoveredDevice] = field(default_factory=list)
    clients: list[DiscoveredClient] = field(default_factory=list)
    links: list[DiscoveredLink] = field(default_factory=list)
    ip_addresses: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # Workload plane (ADR-0015). Empty for every network-facing pack, so a collector that
    # knows nothing about workloads leaves NetBox's virtualization objects untouched.
    clusters: list[DiscoveredCluster] = field(default_factory=list)
    virtual_machines: list[DiscoveredVM] = field(default_factory=list)
    #: Hosts the collector was asked about but could not read. Their clusters are left
    #: alone rather than diffed, so an unreachable host never looks like an emptied stack.
    unreachable_hosts: list[str] = field(default_factory=list)


class Collector(ABC):
    """Observes live network state from one source."""

    #: Stable, unique collector name (used in the registry and as a tool argument).
    name: str = "base"

    @abstractmethod
    async def collect(self) -> DiscoveryResult:
        """Collect current state from this source."""
        raise NotImplementedError
