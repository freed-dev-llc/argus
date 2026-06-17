"""Discovery layer: pluggable collectors that observe live network state."""

from .base import Collector, DiscoveredDevice, DiscoveryResult

__all__ = ["Collector", "DiscoveredDevice", "DiscoveryResult"]
