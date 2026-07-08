"""Guard: ``deploy/docker-compose.yml`` forwards every firewall env var the collector reads.

This wiring is exactly what a code-only change can silently break — the firewall collector
shipped in a past release but the compose file didn't pass its env, so the collector could not
run in the deployed image at all. These offline tests parse the compose file (no Docker, no
secrets, no network) and assert the ``argus-server`` service forwards each ``FIREWALL_<base>``
var for targets 1 and 2, each falling back to the legacy ``PFSENSE_<base>`` name.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from argus.discovery.vendors.firewall.collector import TARGET_ENV_BASES

# server/tests/<this file> -> repo root is two parents up, then deploy/docker-compose.yml.
COMPOSE_PATH = Path(__file__).resolve().parents[2] / "deploy" / "docker-compose.yml"

#: Target suffixes the compose file is expected to forward (target 1 + the documented _2).
FORWARDED_SUFFIXES = ("", "_2")


def _argus_server_env() -> dict[str, str]:
    """Return the ``argus-server`` service's ``environment`` mapping from the compose file."""
    if not COMPOSE_PATH.exists():
        pytest.skip(f"compose file not found at {COMPOSE_PATH} (running outside a full checkout)")
    compose = yaml.safe_load(COMPOSE_PATH.read_text())
    env = compose["services"]["argus-server"]["environment"]
    assert isinstance(env, dict), "argus-server environment must be a mapping (KEY: value form)"
    return env


def test_compose_forwards_every_firewall_target_var() -> None:
    """Each FIREWALL_<base>[_2] the collector reads is forwarded to argus-server."""
    env = _argus_server_env()
    missing = [
        f"FIREWALL_{base}{suffix}"
        for suffix in FORWARDED_SUFFIXES
        for base in TARGET_ENV_BASES
        if f"FIREWALL_{base}{suffix}" not in env
    ]
    assert not missing, (
        f"{COMPOSE_PATH.name} does not forward these firewall vars to argus-server: {missing}. "
        "Add them to the argus-server `environment:` block (see TARGET_ENV_BASES)."
    )


def test_compose_firewall_vars_fall_back_to_pfsense_alias() -> None:
    """Every forwarded FIREWALL_<base>[_2] defaults to its legacy PFSENSE_<base> name, so an
    existing deploy/.env on the old prefix keeps working after the rename."""
    env = _argus_server_env()
    broken = [
        key
        for suffix in FORWARDED_SUFFIXES
        for base in TARGET_ENV_BASES
        if (key := f"FIREWALL_{base}{suffix}") in env
        and f"PFSENSE_{base}{suffix}" not in str(env[key])
    ]
    assert not broken, (
        f"these compose vars do not fall back to their legacy PFSENSE_ alias: {broken}. "
        "Use ${FIREWALL_X:-${PFSENSE_X:-...}} so a pre-rename .env still works."
    )
