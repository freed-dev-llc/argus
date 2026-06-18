"""Tests for the FastAPI HTTP server bearer-token auth gate."""

from __future__ import annotations

from fastapi.testclient import TestClient

from argus.config import get_settings
from argus.http_server import app

client = TestClient(app)

_TOKEN = "s3cret-token"
_PROTECTED = "/api/devices"


def test_protected_route_open_when_token_unset(monkeypatch):
    """With no HTTP_TOKEN configured, protected routes are reachable (auth disabled)."""
    monkeypatch.delenv("HTTP_TOKEN", raising=False)
    get_settings.cache_clear()
    resp = client.get(_PROTECTED)
    assert resp.status_code != 401


def test_protected_route_rejects_missing_header(monkeypatch):
    """A configured token rejects requests with no Authorization header."""
    monkeypatch.setenv("HTTP_TOKEN", _TOKEN)
    get_settings.cache_clear()
    resp = client.get(_PROTECTED)
    assert resp.status_code == 401
    assert resp.json() == {"detail": "unauthorized"}


def test_protected_route_rejects_wrong_token(monkeypatch):
    """A configured token rejects a mismatched bearer token."""
    monkeypatch.setenv("HTTP_TOKEN", _TOKEN)
    get_settings.cache_clear()
    resp = client.get(_PROTECTED, headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 401


def test_protected_route_accepts_correct_token(monkeypatch):
    """A configured token accepts the matching bearer token."""
    monkeypatch.setenv("HTTP_TOKEN", _TOKEN)
    get_settings.cache_clear()
    resp = client.get(_PROTECTED, headers={"Authorization": f"Bearer {_TOKEN}"})
    assert resp.status_code != 401


def test_webhook_route_is_protected(monkeypatch):
    """The webhook prefix is gated alongside /api when a token is set."""
    monkeypatch.setenv("HTTP_TOKEN", _TOKEN)
    get_settings.cache_clear()
    assert client.post("/webhooks/netbox", json={}).status_code == 401
    ok = client.post(
        "/webhooks/netbox", json={}, headers={"Authorization": f"Bearer {_TOKEN}"}
    )
    assert ok.status_code != 401


def test_bearer_scheme_is_case_insensitive(monkeypatch):
    """The ``Bearer`` scheme is matched case-insensitively (RFC 7235)."""
    monkeypatch.setenv("HTTP_TOKEN", _TOKEN)
    get_settings.cache_clear()
    resp = client.get(_PROTECTED, headers={"Authorization": f"bearer {_TOKEN}"})
    assert resp.status_code != 401


def test_cors_preflight_not_gated_when_token_set(monkeypatch):
    """A CORS preflight (OPTIONS) is exempt from auth so the dev server still works.

    Browsers never attach credentials to a preflight; the actual request is still gated.
    """
    monkeypatch.setenv("HTTP_TOKEN", _TOKEN)
    get_settings.cache_clear()
    resp = client.options(
        _PROTECTED,
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code != 401
    assert "access-control-allow-origin" in resp.headers


def test_health_endpoints_public_even_when_token_set(monkeypatch):
    """Health endpoints stay reachable with no token even when auth is enabled."""
    monkeypatch.setenv("HTTP_TOKEN", _TOKEN)
    get_settings.cache_clear()
    assert client.get("/health").status_code == 200
    assert client.get("/health/deep").status_code == 200
