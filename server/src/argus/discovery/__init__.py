"""Discovery layer: pluggable collectors that observe live network state."""

from .base import (
    Collector,
    DiscoveredClient,
    DiscoveredDevice,
    DiscoveredLink,
    DiscoveryResult,
)

__all__ = [
    "Collector",
    "DiscoveredClient",
    "DiscoveredDevice",
    "DiscoveredLink",
    "DiscoveryResult",
]
