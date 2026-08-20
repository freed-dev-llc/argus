"""Docker vendor pack — workload discovery over per-host SSH (ADR-0005, ADR-0015)."""

from __future__ import annotations

from ..pack import WORKLOADS, Transport, VendorPack
from .collector import DockerCollector
from .models import MANUFACTURER

DOCKER_PACK = VendorPack(
    name=DockerCollector.name,
    manufacturer=MANUFACTURER,
    transport=Transport.HOST_SSH,
    # Workload plane only. This pack contributes no devices on purpose: the hosts are real
    # machines other packs already model, and a container runtime is a poor authority on
    # the identity of the metal underneath it.
    capabilities=frozenset({WORKLOADS}),
    config_vars=("DOCKER_HOSTS", "DOCKER_BINARIES", "DOCKER_SSH_TIMEOUT"),
    collector=DockerCollector,
)

__all__ = ["DOCKER_PACK", "DockerCollector"]
