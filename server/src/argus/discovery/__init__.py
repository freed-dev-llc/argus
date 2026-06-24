"""Discovery layer: pluggable collectors that observe live network state."""

from .base import (
    Collector,
    DeviceManagement,
    DiscoveredClient,
    DiscoveredDevice,
    DiscoveredLink,
    DiscoveryResult,
)
from .practices import Finding, Practice, PracticeContext, Severity

__all__ = [
    "Collector",
    "DeviceManagement",
    "DiscoveredClient",
    "DiscoveredDevice",
    "DiscoveredLink",
    "DiscoveryResult",
    "Finding",
    "Practice",
    "PracticeContext",
    "Severity",
]
