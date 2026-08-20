"""Docker workload discovery collector (ADR-0015).

Reads ``docker ps -a`` from each configured host and normalizes the result into clusters
(Compose stacks) and virtual machines (containers). Read-only: the collector never starts,
stops, or changes a container, and the only writes Argus makes are into NetBox via the
reconcile engine (ADR-0003).

Unlike the network packs there is no controller to ask, so acquisition is per host over
SSH (``Transport.HOST_SSH``). Requires ``DOCKER_HOSTS``; see :func:`.models.parse_hosts`.

This pack deliberately emits **no devices**. The hosts are real machines that other packs
(or a human) already model in NetBox, and a container runtime is a poor authority on the
identity of the metal it runs on. It contributes the workload plane only, so a host absent
from NetBox surfaces as an honest unresolved reference rather than a half-invented device.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ....config import get_settings
from ...base import Collector, DiscoveredCluster, DiscoveredVM, DiscoveryResult
from .models import COMPOSE_PROJECT_LABEL, DockerHost, cluster_name, parse_hosts, status_from_state

logger = logging.getLogger(__name__)

#: Field separator for the ``--format`` template. ASCII unit separator, so a container name
#: or stack name containing a pipe or comma cannot split a row into the wrong fields.
_SEP = "\x1f"

_FORMAT = _SEP.join(
    (
        f'{{{{.Label "{COMPOSE_PROJECT_LABEL}"}}}}',
        "{{.Names}}",
        "{{.State}}",
        "{{.Image}}",
    )
)

#: stderr fragments that mean "this host has no Docker", as opposed to "this host is down".
#: A host without Docker legitimately has zero containers; an unreachable one has unknown
#: containers. Conflating them would let an SSH failure empty a stack in the diff.
_NO_DOCKER = ("not found", "no such file", "no such directory")


class DockerCollector(Collector):
    """Collects Compose stacks and containers from a set of Docker hosts."""

    name = "docker"

    def __init__(
        self,
        hosts: list[DockerHost] | None = None,
        *,
        timeout: int | None = None,
    ) -> None:
        settings = get_settings()
        self.hosts = hosts if hosts is not None else parse_hosts(
            settings.docker_hosts, settings.docker_binaries
        )
        self.timeout = timeout if timeout is not None else settings.docker_ssh_timeout

    # --- acquisition -----------------------------------------------------

    def _argv(self, host: DockerHost) -> list[str]:
        command = f"{host.binary} ps -a --no-trunc --format '{_FORMAT}'"
        if host.is_local:
            return ["sh", "-c", command]
        return [
            "ssh",
            "-o",
            f"ConnectTimeout={self.timeout}",
            "-o",
            "BatchMode=yes",
            host.target,
            command,
        ]

    async def _run(self, host: DockerHost) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *self._argv(host),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=self.timeout * 2)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return 124, "", f"timed out after {self.timeout * 2}s"
        return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")

    # --- normalization ---------------------------------------------------

    @staticmethod
    def _rows(stdout: str) -> list[tuple[str, str, str, str]]:
        rows: list[tuple[str, str, str, str]] = []
        for line in stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split(_SEP)
            if len(parts) != 4:
                continue
            project, name, state, image = (p.strip() for p in parts)
            if not name:
                continue
            rows.append((project, name, state, image))
        return rows

    async def _collect_host(self, host: DockerHost, result: DiscoveryResult) -> None:
        code, stdout, stderr = await self._run(host)
        if code != 0:
            lowered = stderr.lower()
            if any(fragment in lowered for fragment in _NO_DOCKER):
                # A real answer: this host runs no containers. Recorded as a note so the
                # zero is visibly deliberate, and NOT as unreachable, so the diff is free
                # to reconcile it down to nothing.
                result.notes.append(f"{host.name}: no docker runtime installed")
                return
            reason = (stderr.strip().splitlines() or ["unknown error"])[-1][:160]
            result.unreachable_hosts.append(host.name)
            result.notes.append(f"{host.name}: not collected ({reason})")
            logger.warning("docker collector could not read %s: %s", host.name, reason)
            return

        seen_clusters: set[str] = set()
        for project, name, state, image in self._rows(stdout):
            cluster = cluster_name(host.name, project or None)
            if cluster not in seen_clusters:
                seen_clusters.add(cluster)
                result.clusters.append(
                    DiscoveredCluster(
                        name=cluster,
                        host=host.name,
                        cluster_type="Docker",
                        status="active",
                        raw={"host": host.name, "project": project},
                    )
                )
            result.virtual_machines.append(
                DiscoveredVM(
                    name=name,
                    cluster=cluster,
                    status=status_from_state(state),
                    raw={"host": host.name, "state": state, "image": image},
                )
            )

    async def collect(self) -> DiscoveryResult:
        result = DiscoveryResult(collector=self.name)
        if not self.hosts:
            result.notes.append("DOCKER_HOSTS is not configured; nothing to collect")
            return result

        # Hosts are independent, and a fleet-wide run is dominated by SSH round-trips.
        await asyncio.gather(*(self._collect_host(h, result) for h in self.hosts))

        # gather() completion order is not input order, and a stable result keeps diffs
        # and test assertions from depending on which host answered first.
        result.clusters.sort(key=lambda c: c.name)
        result.virtual_machines.sort(key=lambda v: (v.cluster, v.name))
        result.unreachable_hosts.sort()
        result.notes.sort()
        return result

    def metadata(self) -> dict[str, Any]:
        return {"hosts": [h.name for h in self.hosts], "timeout": self.timeout}
