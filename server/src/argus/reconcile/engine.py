"""Reconciliation engine: diff observed network state against NetBox, then apply.

Dry-run by default — real writes happen only via :meth:`ReconcileEngine.apply` with
``confirm=True``. The diff/apply internals are stubs (planned P2); see ADR-0003 and
docs/ROADMAP.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ..discovery.base import DiscoveryResult
from ..netbox.client import NetBoxClient

Action = Literal["create", "update", "delete"]


@dataclass
class ReconcileChange:
    """A single proposed change to NetBox."""

    action: Action
    object_type: str
    identifier: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReconcilePlan:
    """A set of proposed changes. Dry-run unless explicitly applied."""

    changes: list[ReconcileChange] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    dry_run: bool = True

    @property
    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for change in self.changes:
            counts[change.action] = counts.get(change.action, 0) + 1
        return {"total": len(self.changes), "by_action": counts, "dry_run": self.dry_run}


class ReconcileEngine:
    """Computes and applies the changes needed to make NetBox match reality."""

    def __init__(self, netbox: NetBoxClient | None = None) -> None:
        self.netbox = netbox

    def diff(self, observed: DiscoveryResult) -> ReconcilePlan:
        """Compute changes needed to make NetBox match observed state (stub)."""
        return ReconcilePlan(
            notes=[
                "Reconcile diff not yet implemented (planned P2). "
                f"Observed {len(observed.devices)} device(s) from '{observed.collector}'."
            ],
        )

    def apply(self, plan: ReconcilePlan, *, confirm: bool = False) -> dict[str, Any]:
        """Apply a plan to NetBox. No-op unless ``confirm`` is set and changes exist."""
        if not confirm or plan.dry_run:
            return {"applied": False, "reason": "dry-run", "summary": plan.summary}
        if not plan.changes:
            return {"applied": False, "reason": "no changes", "summary": plan.summary}
        return {
            "applied": False,
            "reason": "apply not yet implemented (planned P2)",
            "summary": plan.summary,
        }
