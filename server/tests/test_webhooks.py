"""Tests for NetBox webhook event classification and the webhook endpoint.

Auth on ``/webhooks/netbox`` is covered in ``test_http_server.py`` and is not re-tested here.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from argus.config import get_settings
from argus.http_server import app
from argus.webhooks import NetBoxEvent, parse_netbox_event

client = TestClient(app)


def test_parse_created_device():
    """A full created-device payload classifies every field."""
    payload = {
        "event": "created",
        "timestamp": "2026-06-18T10:00:00Z",
        "model": "device",
        "username": "admin",
        "request_id": "req-123",
        "data": {"id": 42, "name": "core-sw-1", "display": "core-sw-1"},
        "snapshots": {"prechange": None, "postchange": {"name": "core-sw-1"}},
    }
    assert parse_netbox_event(payload) == NetBoxEvent(
        event="created",
        model="device",
        object_id=42,
        display="core-sw-1",
        username="admin",
        request_id="req-123",
        timestamp="2026-06-18T10:00:00Z",
    )


def test_parse_updated_ipaddress_falls_back_to_name():
    """``display`` falls back to ``data.name`` when ``data.display`` is absent."""
    payload = {
        "event": "updated",
        "model": "ipaddress",
        "username": "netops",
        "data": {"id": 7, "name": "10.0.0.5/24"},
    }
    event = parse_netbox_event(payload)
    assert event.event == "updated"
    assert event.model == "ipaddress"
    assert event.object_id == 7
    assert event.display == "10.0.0.5/24"
    assert event.username == "netops"


def test_parse_deleted_prefix():
    """A deleted prefix classifies, and an absent field is ``None`` (not an error)."""
    payload = {
        "event": "deleted",
        "model": "prefix",
        "data": {"id": 99, "display": "192.168.0.0/16"},
    }
    event = parse_netbox_event(payload)
    assert event.event == "deleted"
    assert event.model == "prefix"
    assert event.object_id == 99
    assert event.display == "192.168.0.0/16"
    assert event.username is None


def test_parse_empty_dict_yields_all_none():
    """An empty payload yields an all-``None`` event."""
    event = parse_netbox_event({})
    assert event == NetBoxEvent()
    assert all(value is None for value in event.as_dict().values())


def test_parse_non_dict_never_raises():
    """A non-``Mapping`` payload classifies to an all-``None`` event instead of raising."""
    assert parse_netbox_event(["not", "a", "dict"]) == NetBoxEvent()  # type: ignore[arg-type]
    assert parse_netbox_event(None) == NetBoxEvent()  # type: ignore[arg-type]


def test_parse_missing_data_block():
    """A payload with no ``data`` block leaves the object fields ``None``."""
    payload = {"event": "updated", "model": "site", "username": "admin"}
    event = parse_netbox_event(payload)
    assert event.event == "updated"
    assert event.model == "site"
    assert event.object_id is None
    assert event.display is None
    assert event.username == "admin"


def test_summary_is_greppable():
    """The summary line carries the event, model, and display for log grepping."""
    event = parse_netbox_event(
        {"event": "created", "model": "device", "data": {"id": 1, "display": "sw1"}}
    )
    summary = event.summary()
    assert "created" in summary
    assert "device" in summary
    assert "sw1" in summary


def test_webhook_endpoint_acks_classification(monkeypatch):
    """``POST /webhooks/netbox`` acks ``received: True`` plus the classified fields."""
    monkeypatch.delenv("HTTP_TOKEN", raising=False)
    get_settings.cache_clear()
    payload = {
        "event": "created",
        "model": "device",
        "username": "admin",
        "data": {"id": 5, "display": "edge-fw"},
    }
    resp = client.post("/webhooks/netbox", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["received"] is True
    assert body["event"] == "created"
    assert body["model"] == "device"
    assert body["object_id"] == 5
    assert body["display"] == "edge-fw"
