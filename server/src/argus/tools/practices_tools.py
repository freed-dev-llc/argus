"""Practices tool — run a pack's best-practice rules and report findings (ADR-0009).

Read-only / advisory: evaluates each ``VendorPack.practice`` against the live observation plus
a NetBox snapshot and returns findings. Acting on a finding is a separate, confirmation-gated
reconcile step — practices never write.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any

from ..config import get_settings
from ..discovery.practices import Finding, PracticeContext
from ..discovery.vendors import VENDOR_PACKS
from ..netbox.client import NetBoxClient


def _netbox_snapshot() -> tuple[list[dict[str, Any]], bool]:
    """Return (devices, available). Empty + False when NetBox is unconfigured."""
    settings = get_settings()
    if not settings.netbox_configured:
        return [], False
    client = NetBoxClient(
        settings.netbox_url, settings.netbox_token, verify_ssl=settings.netbox_verify_ssl
    )
    return client.list_devices(), True


async def evaluate_practices(collector: str = "unifi") -> dict[str, Any]:
    """Evaluate a vendor pack's best-practice rules against live + NetBox state.

    Runs the pack's collector, builds a context with the observation and a NetBox snapshot,
    runs each declared practice, and returns the findings (read-only — nothing is written).

    Args:
        collector: Pack/collector name from ``list_collectors`` (default "unifi").
    """
    pack = VENDOR_PACKS.get(collector)
    if pack is None:
        return {"error": f"Unknown pack '{collector}'. Available: {sorted(VENDOR_PACKS)}"}

    observed = await pack.collector().collect()
    netbox_devices, netbox_available = await asyncio.to_thread(_netbox_snapshot)
    context = PracticeContext(
        observed=observed, netbox_devices=netbox_devices, netbox_available=netbox_available
    )

    findings: list[Finding] = []
    for practice in pack.practices:
        findings.extend(practice.evaluate(context))

    by_severity: dict[str, int] = {}
    for finding in findings:
        by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1

    return {
        "collector": collector,
        "practices_run": len(pack.practices),
        "netbox_available": netbox_available,
        "summary": {"total": len(findings), "by_severity": by_severity},
        "findings": [asdict(f) for f in findings],
        "notes": observed.notes,
    }
