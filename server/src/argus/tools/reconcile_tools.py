"""Reconciliation tools — review drift and apply changes (confirmation-gated)."""

from __future__ import annotations

from typing import Any

from ..confirmations import ConfirmationStore
from ..discovery.base import DiscoveryResult
from ..reconcile.engine import ReconcileEngine, ReconcilePlan

_store = ConfirmationStore()
_engine = ReconcileEngine()


async def drift_report() -> dict[str, Any]:
    """Report drift between observed network state and NetBox.

    Returns an empty plan today; real drift detection is planned P2 (see ROADMAP).
    """
    plan = _engine.diff(DiscoveryResult(collector="none"))
    return {"summary": plan.summary, "changes": [], "notes": plan.notes}


async def reconcile_apply(confirm_token: str | None = None) -> dict[str, Any]:
    """Apply pending reconciliation changes to NetBox. Confirmation-gated.

    Call once with no token to receive a ``confirm_token`` describing the action, then
    call again with that token to proceed. (The apply itself is stubbed — planned P2.)

    Args:
        confirm_token: The token returned by the first (unconfirmed) call.
    """
    if confirm_token is None:
        action = _store.create(
            tool_name="reconcile_apply",
            description="Apply reconciliation changes to NetBox (mutates the source of truth).",
        )
        return {
            "confirmation_required": True,
            "confirm_token": action.action_id,
            "expires_at": action.expires_at.isoformat(),
            "message": "Re-call reconcile_apply with this confirm_token to proceed.",
        }

    _, error = _store.confirm(confirm_token)
    if error:
        return {"error": error}
    result = _engine.apply(ReconcilePlan(dry_run=False), confirm=True)
    return {"confirmed": True, **result}
