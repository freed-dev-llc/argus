"""Reconciliation tools — review drift and apply changes (confirmation-gated)."""

from __future__ import annotations

import asyncio
import functools
from typing import Any

from ..config import get_settings
from ..confirmations import ConfirmationStore
from ..discovery.base import DiscoveryResult
from ..discovery.collectors import COLLECTORS
from ..netbox.client import NetBoxClient
from ..reconcile.engine import ReconcileChange, ReconcileEngine, ReconcilePlan

_store = ConfirmationStore()
_NOT_CONFIGURED = "NetBox not configured: set NETBOX_URL and NETBOX_TOKEN."


def _engine() -> ReconcileEngine | None:
    """Build a reconcile engine backed by a NetBox client, or None if unconfigured."""
    settings = get_settings()
    if not settings.netbox_configured:
        return None
    client = NetBoxClient(
        settings.netbox_url, settings.netbox_token, verify_ssl=settings.netbox_verify_ssl
    )
    return ReconcileEngine(client)


async def _observe(collector: str) -> DiscoveryResult | None:
    cls = COLLECTORS.get(collector)
    if cls is None:
        return None
    return await cls().collect()


def _change_dict(change: ReconcileChange) -> dict[str, Any]:
    return {
        "action": change.action,
        "object_type": change.object_type,
        "identifier": change.identifier,
        "details": change.details,
    }


async def drift_report(collector: str = "unifi") -> dict[str, Any]:
    """Report drift between observed network state and NetBox.

    Runs a discovery collector, diffs the result against NetBox, and returns the proposed
    changes without applying anything.

    Args:
        collector: Discovery collector to observe with (default "unifi").
    """
    engine = _engine()
    if engine is None:
        return {"error": _NOT_CONFIGURED}
    observed = await _observe(collector)
    if observed is None:
        return {"error": f"Unknown collector '{collector}'. Available: {sorted(COLLECTORS)}"}

    plan = await asyncio.to_thread(engine.diff, observed)
    return {
        "collector": collector,
        "summary": plan.summary,
        "changes": [_change_dict(c) for c in plan.changes],
        "notes": observed.notes + plan.notes,
    }


async def reconcile_apply(collector: str = "unifi", confirm_token: str | None = None) -> dict[str, Any]:
    """Apply reconciliation changes to NetBox. Confirmation-gated.

    Call once with no token to compute a plan and receive a ``confirm_token``; call again
    with that token to apply the plan. An agent cannot mutate the source of truth in a
    single step.

    Args:
        collector: Discovery collector to observe with (default "unifi").
        confirm_token: The token returned by the first (unconfirmed) call.
    """
    engine = _engine()
    if engine is None:
        return {"error": _NOT_CONFIGURED}

    if confirm_token is None:
        observed = await _observe(collector)
        if observed is None:
            return {"error": f"Unknown collector '{collector}'. Available: {sorted(COLLECTORS)}"}
        plan = await asyncio.to_thread(engine.diff, observed)
        if not plan.changes:
            return {
                "applied": False,
                "summary": plan.summary,
                "notes": observed.notes + plan.notes,
                "message": "No changes — NetBox already matches the observed state.",
            }
        action = _store.create(
            tool_name="reconcile_apply",
            description=f"Apply {len(plan.changes)} change(s) to NetBox from '{collector}'.",
            tool_args={"plan": plan},
        )
        return {
            "confirmation_required": True,
            "confirm_token": action.action_id,
            "summary": plan.summary,
            "changes": [_change_dict(c) for c in plan.changes],
            "expires_at": action.expires_at.isoformat(),
            "message": "Re-call reconcile_apply with this confirm_token to apply.",
        }

    pending, error = _store.confirm(confirm_token)
    if error or pending is None:
        return {"error": error or "Action not found."}
    stored_plan: ReconcilePlan = pending.tool_args["plan"]
    result = await asyncio.to_thread(functools.partial(engine.apply, stored_plan, confirm=True))
    return {"confirmed": True, **result}
