"""Tests for the in-process drift scheduler and the optional alert webhook."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from argus import scheduler
from argus.config import get_settings
from argus.http_server import app

_WEBHOOK = "https://hooks.example/alert"


def _drift_result(collector: str, changes: list[dict]) -> dict:
    """A drift_report-shaped success result with the given changes."""
    return {
        "collector": collector,
        "summary": {"create": len(changes)},
        "changes": changes,
        "notes": [],
    }


@pytest.fixture(autouse=True)
def _reset_status():
    """Reset the module-global drift status around each test."""
    scheduler._status = scheduler.DriftStatus()
    yield
    scheduler._status = scheduler.DriftStatus()


@respx.mock
async def test_drift_with_webhook_fires_alert(monkeypatch):
    """Drift present + ALERT_WEBHOOK_URL set → status records drift and a POST fires."""
    monkeypatch.setenv("ALERT_WEBHOOK_URL", _WEBHOOK)
    get_settings.cache_clear()

    async def _fake(collector):
        return _drift_result(collector, [{"action": "create"}])

    monkeypatch.setattr(scheduler, "drift_report", _fake)
    route = respx.post(_WEBHOOK).mock(return_value=httpx.Response(200))

    status = await scheduler.run_drift_cycle("unifi")

    assert status.ok is False
    assert status.change_count == 1
    assert status.error is None
    assert status.last_run is not None
    assert route.called
    body = json.loads(route.calls.last.request.content)
    assert "text" in body
    assert "unifi" in body["text"]


@respx.mock
async def test_no_drift_no_alert(monkeypatch):
    """Empty changes → status ok, and no webhook POST is made even with a URL set."""
    monkeypatch.setenv("ALERT_WEBHOOK_URL", _WEBHOOK)
    get_settings.cache_clear()

    async def _fake(collector):
        return _drift_result(collector, [])

    monkeypatch.setattr(scheduler, "drift_report", _fake)
    respx.post(_WEBHOOK).mock(return_value=httpx.Response(200))

    status = await scheduler.run_drift_cycle("unifi")

    assert status.ok is True
    assert status.change_count == 0
    assert status.error is None
    assert len(respx.calls) == 0


@respx.mock
async def test_error_result_records_error_no_alert(monkeypatch):
    """An ``error`` result is recorded (ok=None) and never triggers a webhook POST."""
    monkeypatch.setenv("ALERT_WEBHOOK_URL", _WEBHOOK)
    get_settings.cache_clear()

    async def _fake(collector):
        return {"error": "NetBox not configured"}

    monkeypatch.setattr(scheduler, "drift_report", _fake)
    respx.post(_WEBHOOK).mock(return_value=httpx.Response(200))

    status = await scheduler.run_drift_cycle("unifi")

    assert status.ok is None
    assert status.error == "NetBox not configured"
    assert status.change_count is None
    assert len(respx.calls) == 0


@respx.mock
async def test_drift_without_webhook_no_alert(monkeypatch):
    """Drift present but no ALERT_WEBHOOK_URL → status records drift, no POST."""
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    get_settings.cache_clear()

    async def _fake(collector):
        return _drift_result(collector, [{"action": "create"}, {"action": "update"}])

    monkeypatch.setattr(scheduler, "drift_report", _fake)

    status = await scheduler.run_drift_cycle("unifi")

    assert status.ok is False
    assert status.change_count == 2
    assert len(respx.calls) == 0


def test_drift_status_endpoint_empty_before_run():
    """``GET /api/drift/status`` returns an empty status before any cycle has run."""
    client = TestClient(app)
    resp = client.get("/api/drift/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["last_run"] is None
    assert body["ok"] is None
    assert body["change_count"] is None


def test_drift_status_endpoint_populated_after_run(monkeypatch):
    """``GET /api/drift/status`` reflects the latest cycle after ``run_drift_cycle``."""
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    get_settings.cache_clear()

    async def _fake(collector):
        return _drift_result(collector, [{"action": "create"}])

    monkeypatch.setattr(scheduler, "drift_report", _fake)
    asyncio.run(scheduler.run_drift_cycle("unifi"))

    client = TestClient(app)
    body = client.get("/api/drift/status").json()
    assert body["collector"] == "unifi"
    assert body["change_count"] == 1
    assert body["ok"] is False
    assert body["last_run"] is not None


async def test_scheduler_loop_runs_one_cycle_then_cancels(monkeypatch):
    """The loop sleeps first, runs a cycle, and stops cleanly on cancellation.

    Deterministic: a stubbed ``asyncio.sleep`` returns on the first call (letting exactly
    one cycle run) and raises ``CancelledError`` on the second to break the loop.
    """
    monkeypatch.setenv("SCHEDULE_INTERVAL", "300")
    get_settings.cache_clear()

    calls: list[str] = []

    async def _fake(collector):
        calls.append(collector)
        return _drift_result(collector, [])

    monkeypatch.setattr(scheduler, "drift_report", _fake)

    counter = {"n": 0}

    async def _fake_sleep(_seconds):
        counter["n"] += 1
        if counter["n"] >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(scheduler.asyncio, "sleep", _fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await scheduler.scheduler_loop()

    assert calls == ["unifi"]
