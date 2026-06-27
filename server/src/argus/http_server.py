"""FastAPI HTTP server — powers the web dashboard and receives NetBox webhooks."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .scheduler import get_drift_status, scheduler_loop
from .tools.discovery_tools import discovery_scan, list_collectors, network_topology
from .tools.practices_tools import evaluate_practices
from .tools.read_tools import (
    get_device,
    list_devices,
    list_ip_addresses,
    list_prefixes,
    search,
)
from .tools.reconcile_tools import drift_report, reconcile_apply
from .webhooks import parse_netbox_event, verify_netbox_signature

logger = logging.getLogger(__name__)

# Routes under these prefixes require a bearer token when one is configured.
_PROTECTED_PREFIXES = ("/api", "/webhooks")
_AUTH_HEADER = "Authorization"
_BEARER_SCHEME = "bearer"

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start the drift scheduler on startup when enabled, and cancel it on shutdown.

    The scheduler is opt-in: it runs only when ``SCHEDULE_INTERVAL`` is positive. When
    disabled this is a no-op, so existing deployments and the plain ``TestClient(app)``
    tests (which never enter the lifespan) are unaffected.
    """
    settings = get_settings()
    task: asyncio.Task[None] | None = None
    if settings.schedule_enabled:
        task = asyncio.create_task(scheduler_loop())
        logger.info("drift scheduler enabled (interval=%ss)", settings.schedule_interval)
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="argus", version="0.1.7", lifespan=lifespan)

# Allow the Vite dev server to call the API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_bearer_token(request: Request, call_next: Any) -> Any:
    """Gate ``/api`` and ``/webhooks`` behind a static bearer token when one is set.

    No-ops when ``HTTP_TOKEN`` is unset (back-compat / dev) and always lets the health
    endpoints through. CORS preflight (``OPTIONS``) is exempt — browsers never attach
    credentials to a preflight, and the actual request is still gated. The token
    comparison is constant-time; the ``Bearer`` scheme is matched case-insensitively.
    """
    settings = get_settings()
    protected = request.url.path.startswith(_PROTECTED_PREFIXES)
    if settings.http_auth_enabled and protected and request.method != "OPTIONS":
        scheme, _, token = request.headers.get(_AUTH_HEADER, "").partition(" ")
        if scheme.lower() != _BEARER_SCHEME or not secrets.compare_digest(
            token, settings.http_token
        ):
            return JSONResponse(
                {"detail": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
    return await call_next(request)


@app.get("/health")
async def health() -> dict[str, str]:
    """Fast liveness check."""
    return {"status": "ok"}


@app.get("/health/deep")
async def health_deep() -> dict[str, Any]:
    """Report whether NetBox is configured."""
    settings = get_settings()
    return {
        "status": "ok" if settings.netbox_configured else "unconfigured",
        "netbox_configured": settings.netbox_configured,
    }


@app.get("/api/devices")
async def api_devices(site: str | None = None, role: str | None = None) -> dict[str, Any]:
    return await list_devices(site=site, role=role)


@app.get("/api/devices/{name}")
async def api_device(name: str) -> dict[str, Any]:
    return await get_device(name)


@app.get("/api/prefixes")
async def api_prefixes() -> dict[str, Any]:
    return await list_prefixes()


@app.get("/api/ip-addresses")
async def api_ip_addresses(prefix: str | None = None) -> dict[str, Any]:
    return await list_ip_addresses(prefix=prefix)


@app.get("/api/search")
async def api_search(q: str) -> dict[str, Any]:
    return await search(q)


@app.get("/api/collectors")
async def api_collectors() -> dict[str, Any]:
    return await list_collectors()


@app.post("/api/collectors/{collector}/scan")
async def api_scan(collector: str) -> dict[str, Any]:
    return await discovery_scan(collector)


@app.get("/api/topology")
async def api_topology(collector: str = "unifi") -> dict[str, Any]:
    return await network_topology(collector)


@app.get("/api/drift")
async def api_drift(collector: str = "unifi") -> dict[str, Any]:
    return await drift_report(collector)


@app.get("/api/practices")
async def api_practices(collector: str = "unifi") -> dict[str, Any]:
    return await evaluate_practices(collector)


@app.get("/api/drift/status")
async def api_drift_status() -> dict[str, Any]:
    """Latest scheduled-drift outcome (or an empty status if the loop never ran)."""
    return get_drift_status().as_dict()


@app.post("/api/reconcile")
async def api_reconcile(
    collector: str = "unifi", confirm_token: str | None = None
) -> dict[str, Any]:
    return await reconcile_apply(collector=collector, confirm_token=confirm_token)


@app.post("/api/ask")
async def api_ask(q: str, pack: str = "ubiquiti") -> dict[str, Any]:
    """Ask the Mnemosyne knowledge brain a question, proxied server-to-server.

    Argus discovers the network; Mnemosyne *explains* it. Returns Mnemosyne's
    ``{answer, sources}`` (or ``{"error": ...}`` if unconfigured/unreachable). Set
    ``MNEMOSYNE_URL`` to the base URL of a ``mnemosyne-http`` service to enable.
    """
    settings = get_settings()
    if not settings.mnemosyne_configured:
        return {"error": "Mnemosyne not configured (set MNEMOSYNE_URL)"}
    url = settings.mnemosyne_url.rstrip("/") + "/ask"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json={"pack": pack, "question": q})
    except httpx.HTTPError as exc:
        return {"error": f"Mnemosyne unreachable: {exc}"}
    if resp.status_code != 200:
        return {"error": f"Mnemosyne returned {resp.status_code}: {resp.text[:200]}"}
    answer: dict[str, Any] = resp.json()
    return answer


@app.post("/webhooks/netbox")
async def netbox_webhook(request: Request) -> Any:
    """Classify and structured-log an inbound NetBox change event, then ack.

    When ``NETBOX_WEBHOOK_SECRET`` is set, the request's ``X-Hook-Signature`` HMAC is verified
    against the raw body first; a missing or mismatched signature is rejected with a 401 before
    parsing. This is additive to the optional ``HTTP_TOKEN`` bearer gate; an unset secret leaves
    verification disabled (back-compat).

    Observability only: the payload is parsed into a :class:`~argus.webhooks.NetBoxEvent`,
    logged as a greppable summary with structured fields, and echoed back as the
    classification. No discovery, reconcile, or NetBox write is triggered (reactions are a
    later phase). Parsing is defensive — a malformed (but authentic) body never raises.
    """
    settings = get_settings()
    raw = await request.body()
    if settings.webhook_verification_enabled and not verify_netbox_signature(
        settings.netbox_webhook_secret, raw, request.headers.get("X-Hook-Signature")
    ):
        return JSONResponse({"detail": "invalid signature"}, status_code=401)
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}
    event = parse_netbox_event(payload if isinstance(payload, dict) else {})
    logger.info("NetBox webhook: %s", event.summary(), extra=event.log_fields())
    return {"received": True, **event.log_fields()}


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.http_host, port=settings.http_port, log_level="info")


if __name__ == "__main__":
    main()
