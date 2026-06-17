"""FastAPI HTTP server — powers the web dashboard and receives NetBox webhooks."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .tools.discovery_tools import discovery_scan, list_collectors, network_topology
from .tools.read_tools import (
    get_device,
    list_devices,
    list_ip_addresses,
    list_prefixes,
    search,
)
from .tools.reconcile_tools import drift_report, reconcile_apply

logger = logging.getLogger(__name__)

app = FastAPI(title="argus", version="0.1.0")

# Allow the Vite dev server to call the API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.post("/api/reconcile")
async def api_reconcile(
    collector: str = "unifi", confirm_token: str | None = None
) -> dict[str, Any]:
    return await reconcile_apply(collector=collector, confirm_token=confirm_token)


@app.post("/webhooks/netbox")
async def netbox_webhook(request: Request) -> dict[str, Any]:
    """Receive NetBox change events (stub — logs and acks; reactions planned P4)."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    event = payload.get("event") if isinstance(payload, dict) else None
    model = payload.get("model") if isinstance(payload, dict) else None
    logger.info("NetBox webhook received: event=%s model=%s", event, model)
    return {"received": True, "event": event, "model": model}


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.http_host, port=settings.http_port, log_level="info")


if __name__ == "__main__":
    main()
