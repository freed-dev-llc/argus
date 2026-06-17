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
class DiscoveredDevice:
    """A device observed on the live network, normalized across collectors."""

    name: str
    mac: str | None = None
    primary_ip: str | None = None
    site: str | None = None
    role: str | None = None
    model: str | None = None
    manufacturer: str | None = None
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
class DiscoveryResult:
    """The normalized output of a single collector run."""

    collector: str
    devices: list[DiscoveredDevice] = field(default_factory=list)
    clients: list[DiscoveredClient] = field(default_factory=list)
    links: list[DiscoveredLink] = field(default_factory=list)
    ip_addresses: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class Collector(ABC):
    """Observes live network state from one source."""

    #: Stable, unique collector name (used in the registry and as a tool argument).
    name: str = "base"

    @abstractmethod
    async def collect(self) -> DiscoveryResult:
        """Collect current state from this source."""
        raise NotImplementedError
