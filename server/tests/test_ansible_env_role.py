"""Guard: the ``argus_deploy`` Ansible role manages real ``deploy/.env`` keys and drops none.

The role once rendered ``deploy/.env`` from a fixed list, so a re-run silently removed every
key it did not know about (bind addresses, the API token pepper, OIDC, collector settings).
These offline tests parse the role's task file and template (no Ansible, no Docker) and
assert that every managed key is a documented stack variable, that the security-relevant keys
are managed explicitly, that generated secrets and optional values are read back from the
existing file, and that the passthrough of unmanaged keys is wired from the task into the
template. ``ansible/playbooks/argus-env-render-check.yml`` is the live counterpart.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / "deploy" / ".env.example"
ROLE_DIR = REPO_ROOT / "ansible" / "roles" / "argus_deploy"
ENV_TASKS = ROLE_DIR / "tasks" / "env.yml"
TEMPLATE = ROLE_DIR / "templates" / "env.j2"

#: Keys whose loss breaks auth, exposure, or token validation; they must be managed, not
#: merely passed through, so a fresh host gets them too.
MUST_MANAGE = {
    "NETBOX_API_TOKEN_PEPPER_1",
    "NETBOX_BIND",
    "ARGUS_WEB_BIND",
    "NETBOX_OIDC_CLIENT_ID",
    "NETBOX_OIDC_CLIENT_SECRET",
    "NETBOX_OIDC_ENDPOINT",
    "NETBOX_OIDC_DEFAULT_GROUPS",
}
#: Generated once, then reused: rotating any of these breaks the running NetBox.
GENERATED_SECRETS = {
    "NETBOX_SECRET_KEY",
    "POSTGRES_PASSWORD",
    "NETBOX_SUPERUSER_PASSWORD",
    "NETBOX_API_TOKEN",
    "NETBOX_API_TOKEN_PEPPER_1",
}
#: The one managed key that is a role setting rather than a value read back from the file.
NOT_READ_BACK = {"NETBOX_IMAGE"}


def _tasks() -> list[dict]:
    for path in (ENV_EXAMPLE, ENV_TASKS, TEMPLATE):
        if not path.exists():
            pytest.skip(f"{path} not found (running outside a full checkout)")
    tasks = yaml.safe_load(ENV_TASKS.read_text())
    assert isinstance(tasks, list), "tasks/env.yml must be a task list"
    return tasks


def _managed() -> dict[str, str]:
    for task in _tasks():
        fact = task.get("ansible.builtin.set_fact") or {}
        if "argus_env" in fact:
            return fact["argus_env"]
    raise AssertionError("no set_fact task in tasks/env.yml defines argus_env")


def _example_keys() -> set[str]:
    return set(re.findall(r"^([A-Z0-9_]+)=", ENV_EXAMPLE.read_text(), re.MULTILINE))


def test_every_managed_key_is_a_documented_stack_variable() -> None:
    unknown = set(_managed()) - _example_keys()
    assert not unknown, f"argus_env manages keys absent from deploy/.env.example: {sorted(unknown)}"


def test_security_relevant_keys_are_managed_explicitly() -> None:
    missing = MUST_MANAGE - set(_managed())
    assert not missing, f"argus_env must manage: {sorted(missing)}"


def test_generated_secrets_are_reused_from_the_existing_file() -> None:
    managed = _managed()
    for key in sorted(GENERATED_SECRETS):
        expr = managed[key]
        assert f"argus_existing.{key}" in expr, f"{key} is not reused from the existing .env"
        assert "lookup('ansible.builtin.password'" in expr, f"{key} is not generated when absent"


def test_optional_values_read_back_the_existing_file_when_blank() -> None:
    for key, expr in _managed().items():
        if key in NOT_READ_BACK:
            continue
        assert f"argus_existing.{key}" in expr, f"{key} would be reset on every run"


def test_unmanaged_keys_pass_through_to_the_template() -> None:
    facts = [t.get("ansible.builtin.set_fact") or {} for t in _tasks()]
    assert any("argus_env_passthrough" in f for f in facts), "no passthrough set_fact"
    template = TEMPLATE.read_text()
    assert "argus_env.items()" in template, "template does not render the managed keys"
    assert "argus_env_passthrough.items()" in template, "template drops unmanaged keys"
