"""Tests for the FastAPI HTTP server bearer-token auth gate."""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import respx
from fastapi.testclient import TestClient

from argus.config import get_settings
from argus.http_server import app

client = TestClient(app)

_TOKEN = "s3cret-token"
_PROTECTED = "/api/devices"

_WEBHOOK_SECRET = "webhook-hmac-secret"
_WEBHOOK_PAYLOAD = {
    "event": "created",
    "model": "device",
    "username": "admin",
    "data": {"id": 5, "display": "edge-fw"},
}
# Byte-exact body the signature is computed over (mirrors what we POST to the server).
_WEBHOOK_BODY = json.dumps(_WEBHOOK_PAYLOAD).encode("utf-8")
_JSON_HEADERS = {"Content-Type": "application/json"}


def _hook_signature(secret: str, body: bytes) -> str:
    """Compute the NetBox X-Hook-Signature (HMAC-SHA512 hexdigest) for ``body``."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha512).hexdigest()


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


def test_api_ask_unconfigured_returns_error(monkeypatch):
    """With no MNEMOSYNE_URL set, /api/ask returns a clear error (feature disabled)."""
    monkeypatch.delenv("HTTP_TOKEN", raising=False)
    monkeypatch.delenv("MNEMOSYNE_URL", raising=False)
    get_settings.cache_clear()
    resp = client.post("/api/ask?q=anything")
    assert resp.status_code == 200
    assert "error" in resp.json()


@respx.mock
def test_api_ask_proxies_to_mnemosyne(monkeypatch):
    """/api/ask proxies the question to MNEMOSYNE_URL and returns its answer + sources."""
    monkeypatch.delenv("HTTP_TOKEN", raising=False)
    monkeypatch.setenv("MNEMOSYNE_URL", "http://mnemo.test:8088")
    get_settings.cache_clear()
    route = respx.post("http://mnemo.test:8088/ask").mock(
        return_value=httpx.Response(
            200,
            json={"answer": "Adopt it over L3.", "sources": [{"title": "Remote Adoption"}]},
        )
    )
    resp = client.post("/api/ask?q=how+do+I+adopt+remotely")
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Adopt it over L3."
    assert body["sources"][0]["title"] == "Remote Adoption"
    assert route.called


def test_webhook_open_when_secret_unset(monkeypatch):
    """With no NETBOX_WEBHOOK_SECRET set, the webhook accepts unsigned posts (back-compat)."""
    monkeypatch.delenv("HTTP_TOKEN", raising=False)
    monkeypatch.delenv("NETBOX_WEBHOOK_SECRET", raising=False)
    get_settings.cache_clear()
    resp = client.post("/webhooks/netbox", json=_WEBHOOK_PAYLOAD)
    assert resp.status_code == 200
    assert resp.json()["received"] is True


def test_webhook_rejects_missing_signature(monkeypatch):
    """A configured secret rejects a post with no X-Hook-Signature header (401)."""
    monkeypatch.delenv("HTTP_TOKEN", raising=False)
    monkeypatch.setenv("NETBOX_WEBHOOK_SECRET", _WEBHOOK_SECRET)
    get_settings.cache_clear()
    resp = client.post("/webhooks/netbox", content=_WEBHOOK_BODY, headers=_JSON_HEADERS)
    assert resp.status_code == 401
    assert resp.json() == {"detail": "invalid signature"}


def test_webhook_rejects_invalid_signature(monkeypatch):
    """A configured secret rejects a post whose X-Hook-Signature does not match (401)."""
    monkeypatch.delenv("HTTP_TOKEN", raising=False)
    monkeypatch.setenv("NETBOX_WEBHOOK_SECRET", _WEBHOOK_SECRET)
    get_settings.cache_clear()
    resp = client.post(
        "/webhooks/netbox",
        content=_WEBHOOK_BODY,
        headers={**_JSON_HEADERS, "X-Hook-Signature": "deadbeef"},
    )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "invalid signature"}


def test_webhook_accepts_correct_signature(monkeypatch):
    """A configured secret accepts a correctly-signed post and returns the classification."""
    monkeypatch.delenv("HTTP_TOKEN", raising=False)
    monkeypatch.setenv("NETBOX_WEBHOOK_SECRET", _WEBHOOK_SECRET)
    get_settings.cache_clear()
    sig = _hook_signature(_WEBHOOK_SECRET, _WEBHOOK_BODY)
    resp = client.post(
        "/webhooks/netbox",
        content=_WEBHOOK_BODY,
        headers={**_JSON_HEADERS, "X-Hook-Signature": sig},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["received"] is True
    assert body["event"] == "created"
    assert body["model"] == "device"
    assert body["object_id"] == 5
    assert body["display"] == "edge-fw"


def test_webhook_bearer_and_signature_both_apply(monkeypatch):
    """When both HTTP_TOKEN and the secret are set, both checks gate the webhook.

    Validates the additive layering: a correctly-signed post still needs the bearer token,
    and a bearer-authenticated post still needs a valid signature.
    """
    monkeypatch.setenv("HTTP_TOKEN", _TOKEN)
    monkeypatch.setenv("NETBOX_WEBHOOK_SECRET", _WEBHOOK_SECRET)
    get_settings.cache_clear()
    sig = _hook_signature(_WEBHOOK_SECRET, _WEBHOOK_BODY)
    # Correct signature but no bearer token → blocked by the bearer middleware first.
    no_bearer = client.post(
        "/webhooks/netbox",
        content=_WEBHOOK_BODY,
        headers={**_JSON_HEADERS, "X-Hook-Signature": sig},
    )
    assert no_bearer.status_code == 401
    assert no_bearer.json() == {"detail": "unauthorized"}
    # Bearer token but missing signature → blocked by the HMAC check.
    no_sig = client.post(
        "/webhooks/netbox",
        content=_WEBHOOK_BODY,
        headers={**_JSON_HEADERS, "Authorization": f"Bearer {_TOKEN}"},
    )
    assert no_sig.status_code == 401
    assert no_sig.json() == {"detail": "invalid signature"}
    # Both present and valid → accepted.
    ok = client.post(
        "/webhooks/netbox",
        content=_WEBHOOK_BODY,
        headers={
            **_JSON_HEADERS,
            "Authorization": f"Bearer {_TOKEN}",
            "X-Hook-Signature": sig,
        },
    )
    assert ok.status_code == 200
    assert ok.json()["received"] is True
