"""Docker workload discovery collector (ADR-0015).

Reads ``docker ps -a`` from each configured host and normalizes the result into clusters
(Compose stacks) and virtual machines (containers). Read-only: the collector never starts,
stops, or changes a container, and the only writes Argus makes are into NetBox via the
reconcile engine (ADR-0003).

Unlike the network packs there is no controller to ask, so acquisition is per host over
SSH (``Transport.HOST_SSH``). Requires ``DOCKER_HOSTS``; see :func:`.models.parse_hosts`.

Remote hosts are reached with **asyncssh**, not by shelling out to the ``ssh`` binary.
The deployed image (``python:3.13-slim``) ships asyncssh and has no ``ssh`` binary at
all, so a subprocess implementation could not run where this pack is meant to run. It
also matches the firewall pack, which has used asyncssh since ADR-0013, and it replaces
matching on stderr text with real exception types: a refused connection, a rejected key,
and a host that simply has no Docker are three different outcomes, and only the last one
means "this host really runs zero containers".

This pack deliberately emits **no devices**. The hosts are real machines that other packs
(or a human) already model in NetBox, and a container runtime is a poor authority on the
identity of the metal it runs on. It contributes the workload plane only, so a host absent
from NetBox surfaces as an honest unresolved reference rather than a half-invented device.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
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
#: containers. Conflating them would let an SSH failure empty a stack in the diff. This is
#: still text matching, but it now only has to classify a *shell* failure (127 and friends);
#: transport and auth failures are exceptions and never reach here.
_NO_DOCKER = ("not found", "no such file", "no such directory")

#: Returned by :meth:`DockerCollector._run` when the host could not be reached or
#: authenticated at all, as distinct from a command that ran and failed. Negative so it
#: cannot collide with a real POSIX exit status.
CONNECT_FAILED = -1


def _text(value: Any) -> str:
    """asyncssh can hand back str or bytes; normalize (the firewall pack does the same)."""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""


class DockerCollector(Collector):
    """Collects Compose stacks and containers from a set of Docker hosts."""

    name = "docker"

    def __init__(
        self,
        hosts: list[DockerHost] | None = None,
        *,
        timeout: int | None = None,
        ssh_key: str | None = None,
        ssh_config: str | None = None,
        known_hosts: str | None = None,
    ) -> None:
        settings = get_settings()
        self.hosts = hosts if hosts is not None else parse_hosts(
            settings.docker_hosts, settings.docker_binaries
        )
        self.timeout = timeout if timeout is not None else settings.docker_ssh_timeout
        self.ssh_key = (ssh_key if ssh_key is not None else settings.docker_ssh_key).strip()
        self.ssh_config = (
            ssh_config if ssh_config is not None else settings.docker_ssh_config
        ).strip()
        self.known_hosts = (
            known_hosts if known_hosts is not None else settings.docker_ssh_known_hosts
        ).strip()

    # --- acquisition -----------------------------------------------------

    def _command(self, host: DockerHost) -> str:
        return f"{host.binary} ps -a --no-trunc --format '{_FORMAT}'"

    def _connect_options(self, host: DockerHost) -> dict[str, Any]:
        """Build asyncssh.connect kwargs for one host.

        Host-key policy defaults to asyncssh's, which verifies against the user's
        known_hosts and refuses an unknown host. That deliberately matches what the
        previous ``ssh`` subprocess did (BatchMode fails rather than prompts) instead of
        the firewall pack's ``known_hosts=None``: that pack talks to one appliance with a
        password, while this one holds shells across the whole fleet. ``DOCKER_SSH_KNOWN_HOSTS``
        set to "none" opts out explicitly, which is a choice an operator has to make rather
        than inherit.
        """
        username, hostname, port = host.ssh_target
        opts: dict[str, Any] = {"connect_timeout": self.timeout}
        if username:
            opts["username"] = username
        if port:
            opts["port"] = port
        if self.ssh_key:
            opts["client_keys"] = [os.path.expanduser(self.ssh_key)]
        # ssh_config is what makes an alias like "thor" resolve; asyncssh does not read it
        # unless asked. Only pass a file that exists, or asyncssh raises on a missing path.
        cfg = os.path.expanduser(self.ssh_config or "~/.ssh/config")
        if os.path.isfile(cfg):
            opts["config"] = [cfg]
        if self.known_hosts:
            opts["known_hosts"] = (
                None if self.known_hosts.lower() in {"none", "off", "disabled"}
                else os.path.expanduser(self.known_hosts)
            )
        opts["_hostname"] = hostname
        return opts

    async def _run(self, host: DockerHost) -> tuple[int, str, str]:
        """Return (exit_status, stdout, stderr), or CONNECT_FAILED and a reason.

        CONNECT_FAILED means the host was never reached or never authenticated, which is
        categorically different from a command that ran and failed: the first leaves this
        host's containers unknown, the second can still be a real answer.
        """
        if host.is_local:
            return await self._run_local(host)
        return await self._run_ssh(host)

    async def _run_local(self, host: DockerHost) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            "sh",
            "-c",
            self._command(host),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=self.timeout * 2)
        except TimeoutError:
            proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
            return CONNECT_FAILED, "", f"timed out after {self.timeout * 2}s"
        return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")

    async def _run_ssh(self, host: DockerHost) -> tuple[int, str, str]:
        try:
            import asyncssh
        except ImportError as exc:  # pragma: no cover - packaged as a runtime dep
            raise ImportError(
                "asyncssh not installed; install with: pip install 'argus[discovery]'"
            ) from exc

        opts = self._connect_options(host)
        hostname = opts.pop("_hostname")
        try:
            async with asyncssh.connect(hostname, **opts) as conn:
                result = await asyncio.wait_for(
                    conn.run(self._command(host), check=False),
                    timeout=self.timeout * 2,
                )
        except asyncssh.PermissionDenied as exc:
            return CONNECT_FAILED, "", f"ssh authentication failed: {exc}"
        except asyncssh.HostKeyNotVerifiable as exc:
            return CONNECT_FAILED, "", f"ssh host key not verifiable: {exc}"
        except TimeoutError:
            return CONNECT_FAILED, "", f"timed out after {self.timeout * 2}s"
        except (OSError, asyncssh.Error) as exc:
            return CONNECT_FAILED, "", f"ssh connection failed: {exc}"
        return (
            result.exit_status or 0,
            _text(result.stdout),
            _text(result.stderr),
        )

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
        if code == CONNECT_FAILED:
            # Never reached or never authenticated. Its containers are unknown, so the
            # host is recorded and its clusters are left out of the diff entirely.
            reason = (stderr.strip().splitlines() or ["unknown error"])[-1][:160]
            result.unreachable_hosts.append(host.name)
            result.notes.append(f"{host.name}: not collected ({reason})")
            logger.warning("docker collector could not reach %s: %s", host.name, reason)
            return
        if code != 0:
            lowered = stderr.lower()
            if any(fragment in lowered for fragment in _NO_DOCKER):
                # A real answer: this host runs no containers. Recorded as a note so the
                # zero is visibly deliberate, and NOT as unreachable, so the diff is free
                # to reconcile it down to nothing.
                result.notes.append(f"{host.name}: no docker runtime installed")
                return
            # The shell ran and the command failed for some other reason (a root-owned
            # socket, a broken daemon). Still unknown, so still not a zero.
            reason = (stderr.strip().splitlines() or [f"exit status {code}"])[-1][:160]
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
        return {
            "hosts": [h.name for h in self.hosts],
            "timeout": self.timeout,
            "transport": "asyncssh",
            "ssh_key": bool(self.ssh_key),
            "host_key_checking": self.known_hosts.lower() not in {"none", "off", "disabled"},
        }
