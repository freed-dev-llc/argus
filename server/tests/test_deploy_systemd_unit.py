"""Guard: ``deploy/argus.service`` checks the same mesh-bound ports the compose file publishes.

The unit repairs port bindings lost at boot when ``NETBOX_BIND`` / ``ARGUS_WEB_BIND`` point at
an overlay address that Docker tries to bind before the interface exists. Its checks are
hand-written ``docker compose port <service> <container-port>`` lines, so a compose change (a
new mesh-bound service, a renamed service, a moved container port) can silently leave a
service unrepaired. These offline tests parse both files (no Docker, no secrets, no network)
and assert they agree.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

DEPLOY_DIR = Path(__file__).resolve().parents[2] / "deploy"
COMPOSE_PATH = DEPLOY_DIR / "docker-compose.yml"
UNIT_PATH = DEPLOY_DIR / "argus.service"

#: ``docker compose --env-file .env port <service> <container-port>`` as written in the unit.
_PORT_CHECK = re.compile(r"docker compose --env-file \.env port (\S+) (\d+)")
#: ``${VAR:-default}:<host-port>:<container-port>`` as written in the compose ``ports`` lists.
_BIND_VAR_PORT = re.compile(r"^\$\{(\w+):-[^}]*\}:(\d+):(\d+)$")


def _mesh_bound_services() -> dict[str, tuple[str, int]]:
    """Map each service with a ``${VAR:-...}``-bound port to ``(VAR, container_port)``."""
    if not COMPOSE_PATH.exists() or not UNIT_PATH.exists():
        pytest.skip("deploy/ files not found (running outside a full checkout)")
    compose = yaml.safe_load(COMPOSE_PATH.read_text())
    found: dict[str, tuple[str, int]] = {}
    for name, service in compose["services"].items():
        for port in service.get("ports") or []:
            match = _BIND_VAR_PORT.match(str(port))
            if match:
                found[name] = (match.group(1), int(match.group(3)))
    assert found, "expected at least one ${VAR:-...}-bound port in the compose file"
    return found


def _unit_port_checks() -> dict[str, int]:
    """Map each service the unit checks to the container port it asks ``compose port`` about."""
    checks = {svc: int(port) for svc, port in _PORT_CHECK.findall(UNIT_PATH.read_text())}
    assert checks, "argus.service has no `docker compose port` checks"
    return checks


def test_unit_checks_every_mesh_bound_service_on_its_container_port() -> None:
    """Every bind-parameterized service is checked, on the container port compose publishes."""
    bound = _mesh_bound_services()
    checks = _unit_port_checks()
    for svc, (_, container_port) in bound.items():
        assert svc in checks, f"{svc} has a bind-parameterized port but argus.service never checks it"
        assert checks[svc] == container_port, (
            f"{svc}: argus.service checks port {checks[svc]}, compose publishes {container_port}"
        )


def test_unit_checks_only_services_with_a_bind_parameterized_port() -> None:
    """A stale check for a renamed or de-parameterized service fails loudly here."""
    bound = _mesh_bound_services()
    for svc in _unit_port_checks():
        assert svc in bound, f"argus.service checks {svc}, which has no bind-parameterized port"


def test_unit_waits_on_every_bind_variable() -> None:
    """The ExecStartPre loop reads each bind variable the compose file uses."""
    bound = _mesh_bound_services()
    pre = [ln for ln in UNIT_PATH.read_text().splitlines() if ln.startswith("ExecStartPre=")]
    assert len(pre) == 1, "expected exactly one ExecStartPre wait loop"
    for var in {var for var, _ in bound.values()}:
        assert var in pre[0], f"ExecStartPre does not wait for {var}"


def test_unit_has_no_execstop() -> None:
    """Docker's restart policy owns shutdown; a compose stop here would bounce the stack."""
    assert not re.search(r"^ExecStop=", UNIT_PATH.read_text(), re.MULTILINE)
