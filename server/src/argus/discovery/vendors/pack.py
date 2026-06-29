"""Vendor pack SPI — the stable contract external (incl. private) packs build against.

A :class:`VendorPack` bundles everything Argus needs to integrate one vendor/technology:
the live :class:`~argus.discovery.base.Collector` adapter plus declarative metadata
(manufacturer, transport, capabilities, the config variables it consumes). Packs are
discovered by :mod:`argus.discovery.vendors` — either built-in (in this repo) or from any
installed distribution that advertises an ``argus.vendor_packs`` entry point. See ADR-0005.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ..base import Collector
from ..practices import Practice

#: Entry-point group an external distribution uses to register its packs. Each entry
#: point must resolve to a :class:`VendorPack` instance, e.g. in its ``pyproject.toml``::
#:
#:     [project.entry-points."argus.vendor_packs"]
#:     aruba_central = "argus_vendor_packs.aruba_central:ARUBA_CENTRAL_PACK"
ENTRY_POINT_GROUP = "argus.vendor_packs"

# Capability tokens (typo-safe set members for VendorPack.capabilities).
DEVICES = "devices"
CLIENTS = "clients"
TOPOLOGY = "topology"
CONFIG = "config"


class Transport(StrEnum):
    """How a pack reaches the network — shapes acquisition, not the normalized output."""

    CONTROLLER_API = "controller_api"  # one cloud/controller API yields many devices
    DEVICE_SNMP = "device_snmp"  # per-device SNMP
    DEVICE_SSH = "device_ssh"  # per-device SSH / CLI


@dataclass(frozen=True)
class VendorPack:
    """Declarative integration descriptor for one vendor/technology (ADR-0005)."""

    #: Stable, unique pack/collector name (the discovery-tool argument, e.g. "unifi").
    name: str
    #: NetBox manufacturer this pack's devices map to (e.g. "Ubiquiti").
    manufacturer: str
    transport: Transport
    capabilities: frozenset[str]
    #: Settings/env vars this pack consumes (documentation + future validation).
    config_vars: tuple[str, ...]
    collector: type[Collector]
    #: Best-practice / validation rules this pack ships (ADR-0009); empty by default.
    practices: tuple[Practice, ...] = field(default_factory=tuple)
    #: Name of the Mnemosyne knowledge pack that *explains* this vendor. The discovery face
    #: (this pack) and the knowledge face share a vendor but not necessarily a name (e.g.
    #: discovery "unifi" ↔ knowledge "ubiquiti"). Surfaced in collector metadata so the
    #: dashboard's "Ask the Brain" panel queries the right pack instead of a hardcoded
    #: default. ``None`` (default) = this vendor has no paired knowledge pack yet. ADR-0013.
    knowledge_pack: str | None = None
