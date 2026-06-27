"""Tests for opt-in, read-only webhook reactions.

Covers the pure :func:`should_react` predicate and the single-flight + trailing-coalesce
trigger mechanism. ``run_drift_cycle`` is mocked throughout, so nothing hits a real collector
or NetBox and the tests pass offline.
"""

from __future__ import annotations

import asyncio

import pytest

from argus import reactions, scheduler
from argus.config import Settings
from argus.webhooks import NetBoxEvent


def _settings(
    *,
    reactions_enabled: bool = True,
    http_token: str = "tok",
    webhook_secret: str = "",
    models: str = "dcim.device,ipam.ipaddress",
) -> Settings:
    """Build a Settings with the reaction-relevant fields pinned (env-independent)."""
    return Settings(
        webhook_reactions_enabled=reactions_enabled,
        http_token=http_token,
        netbox_webhook_secret=webhook_secret,
        webhook_reaction_models=models,
    )


@pytest.fixture(autouse=True)
def _reset_reactions():
    """Reset the single-flight/coalesce module state around each test."""
    reactions.reset_state()
    yield
    reactions.reset_state()


# --- should_react (pure predicate) ---


def test_should_react_true_when_enabled_authentic_matching():
    """Enabled + authenticated (bearer) + allow-listed model → react."""
    settings = _settings(reactions_enabled=True, http_token="tok")
    assert reactions.should_react(NetBoxEvent(model="dcim.device"), settings) is True


def test_should_react_true_with_hmac_auth_only():
    """Authenticity may come from webhook HMAC verification alone (no bearer token)."""
    settings = _settings(reactions_enabled=True, http_token="", webhook_secret="hmac")
    assert reactions.should_react(NetBoxEvent(model="dcim.device"), settings) is True


def test_should_react_false_when_disabled():
    """Disabled (default) → never react, even when authenticated and allow-listed."""
    settings = _settings(reactions_enabled=False, http_token="tok")
    assert reactions.should_react(NetBoxEvent(model="dcim.device"), settings) is False


def test_should_react_false_when_no_auth_configured():
    """Open endpoint (no bearer, no HMAC secret) → never react off a forgeable event."""
    settings = _settings(reactions_enabled=True, http_token="", webhook_secret="")
    assert reactions.should_react(NetBoxEvent(model="dcim.device"), settings) is False


def test_should_react_false_when_model_not_allowed():
    """A model outside the allow-list is classified/logged but triggers nothing."""
    settings = _settings(reactions_enabled=True, http_token="tok")
    assert reactions.should_react(NetBoxEvent(model="dcim.site"), settings) is False


def test_should_react_false_when_model_none():
    """A missing model never matches the allow-list."""
    settings = _settings(reactions_enabled=True, http_token="tok")
    assert reactions.should_react(NetBoxEvent(model=None), settings) is False


# --- trigger mechanism (single-flight + trailing-coalesce) ---


async def test_single_event_runs_exactly_one_cycle(monkeypatch):
    """One event → exactly one drift cycle, and module state resets when it finishes."""
    calls: list[str] = []

    async def _fake(collector):
        calls.append(collector)

    monkeypatch.setattr(scheduler, "run_drift_cycle", _fake)

    task = reactions.trigger_reaction("unifi")
    assert task is not None
    await task

    assert calls == ["unifi"]
    assert reactions._running is False
    assert reactions._pending is False
    assert reactions._task is None


async def test_burst_coalesces_to_one_plus_one_trailing(monkeypatch):
    """A burst arriving while a cycle is in flight collapses to 1 + at most 1 trailing."""
    calls: list[str] = []
    started = asyncio.Event()
    release = asyncio.Event()

    async def _fake(collector):
        calls.append(collector)
        started.set()
        await release.wait()

    monkeypatch.setattr(scheduler, "run_drift_cycle", _fake)

    task = reactions.trigger_reaction("unifi")  # leading cycle starts
    await started.wait()                         # leading cycle is now in flight

    # Five events during the in-flight cycle all coalesce into a single pending flag and
    # return the same in-flight task — no second concurrent cycle is started.
    for _ in range(5):
        assert reactions.trigger_reaction("unifi") is task
    assert reactions._pending is True

    release.set()                                # let the leading + trailing cycles complete
    await task

    assert calls == ["unifi", "unifi"]           # exactly 1 + 1 trailing, not 6
    assert reactions._running is False
    assert reactions._pending is False
    assert reactions._task is None


async def test_raising_cycle_is_swallowed_and_clears_state(monkeypatch):
    """A cycle that raises is caught/logged; the task never raises and state is reset."""

    async def _boom(collector):
        raise RuntimeError("collector exploded")

    monkeypatch.setattr(scheduler, "run_drift_cycle", _boom)

    task = reactions.trigger_reaction("unifi")
    assert task is not None
    await task  # must not raise

    assert reactions._running is False
    assert reactions._pending is False
    assert reactions._task is None
