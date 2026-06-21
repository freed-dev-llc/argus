"""Example collector skeleton — implement ``collect()`` against your vendor's API/protocol.

Collectors are READ-ONLY against the network: the only writes Argus makes are into NetBox,
via the reconcile engine. Return a normalized :class:`DiscoveryResult`.
"""

from __future__ import annotations

from argus.discovery.base import Collector, DiscoveredDevice, DiscoveryResult

from .models import MANUFACTURER, role_from_model


class ExampleCollector(Collector):
    name = "example"

    async def collect(self) -> DiscoveryResult:
        result = DiscoveryResult(collector=self.name)

        # 1) Read config/credentials. Use your own env vars, or argus's settings:
        #        from argus.config import get_settings
        #    Guard the unconfigured case so a scan degrades gracefully:
        #        result.notes.append("example pack not configured: set EXAMPLE_API_TOKEN")
        #        return result
        #
        # 2) Call your vendor API / poll devices (read-only).
        #
        # 3) Normalize each device, e.g.:
        #        result.devices.append(DiscoveredDevice(
        #            name=device["name"], mac=device.get("mac"), primary_ip=device.get("ip"),
        #            site=site_name, role=role_from_model(device.get("model")),
        #            model=device.get("model"), manufacturer=MANUFACTURER, raw=device,
        #        ))
        #    Optionally populate result.clients / result.links / result.ip_addresses.

        _ = (DiscoveredDevice, MANUFACTURER, role_from_model)  # referenced in the steps above
        result.notes.append("example vendor pack template — implement ExampleCollector.collect().")
        return result
