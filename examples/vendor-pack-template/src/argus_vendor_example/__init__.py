"""Example Argus vendor pack — a copy-to-start template (ADR-0005). Not for production use."""

from __future__ import annotations

from argus.discovery.vendors.pack import DEVICES, Transport, VendorPack

from .collector import ExampleCollector
from .models import MANUFACTURER

#: The entry point (see pyproject.toml) resolves to this instance.
EXAMPLE_PACK = VendorPack(
    name=ExampleCollector.name,
    manufacturer=MANUFACTURER,
    transport=Transport.CONTROLLER_API,  # or Transport.DEVICE_SNMP / DEVICE_SSH
    capabilities=frozenset({DEVICES}),  # add CLIENTS / TOPOLOGY / CONFIG as you implement them
    config_vars=("EXAMPLE_URL", "EXAMPLE_API_TOKEN"),
    collector=ExampleCollector,
)

__all__ = ["EXAMPLE_PACK", "ExampleCollector"]
