"""Vendor pack registry — built-in packs + out-of-tree packs via entry points (ADR-0005).

Built-in packs (shipped in this repo) are registered directly so dev/CI needs no install
step. **External** packs — including private, MSP-supported vendors — register by being
installed alongside Argus and advertising an ``argus.vendor_packs`` entry point; this repo
contains none of that code and names none of those vendors. A broken external pack is
skipped (logged), never crashing discovery.
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points

from ..base import Collector
from .pack import ENTRY_POINT_GROUP, Transport, VendorPack
from .unifi import UNIFI_PACK

logger = logging.getLogger(__name__)

#: Packs shipped in this (public) repo. External packs attach via the entry point.
BUILTIN_PACKS: tuple[VendorPack, ...] = (UNIFI_PACK,)


def _load_entry_point_packs() -> list[VendorPack]:
    found: list[VendorPack] = []
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        try:
            pack = ep.load()
        except Exception as exc:  # a broken external pack must not break discovery
            logger.warning("skipping vendor pack entry point %r: %s", ep.name, exc)
            continue
        if isinstance(pack, VendorPack):
            found.append(pack)
        else:
            logger.warning(
                "vendor pack entry point %r resolved to %r, not a VendorPack", ep.name, type(pack)
            )
    return found


def discover_packs() -> dict[str, VendorPack]:
    """Merge built-in packs with installed external packs (built-ins win on name clash)."""
    packs: dict[str, VendorPack] = {pack.name: pack for pack in BUILTIN_PACKS}
    for pack in _load_entry_point_packs():
        if pack.name in packs:
            logger.warning("vendor pack %r already registered; ignoring duplicate", pack.name)
            continue
        packs[pack.name] = pack
    return packs


#: All registered packs (built-in + external), keyed by name.
VENDOR_PACKS: dict[str, VendorPack] = discover_packs()


def vendor_collectors() -> dict[str, type[Collector]]:
    """Name → Collector class for every registered vendor pack (feeds ``COLLECTORS``)."""
    return {name: pack.collector for name, pack in VENDOR_PACKS.items()}


__all__ = [
    "BUILTIN_PACKS",
    "ENTRY_POINT_GROUP",
    "Transport",
    "VENDOR_PACKS",
    "VendorPack",
    "discover_packs",
    "vendor_collectors",
]
