"""Reconciliation engine: diff observed network state against NetBox, then apply.

The engine is the core of Argus: it computes the changes needed to make NetBox (the
source of truth) reflect what discovery actually observed, and — only on explicit
confirmation — applies them. See ADR-0003.

**Scope (P2, issue #10):**
- ``diff()`` is complete: matches observed devices to NetBox by name, proposes ``create``
  for observed-only devices and ``update`` for field drift (``primary_ip``), and reports
  NetBox-only devices as notes (never auto-deleted — too risky with partial discovery).
- ``apply()`` is the confirmation-gated write mechanism: it dispatches per change and
  captures per-change success/failure. Resolving discovery values into NetBox foreign
  keys (sites/roles/device-types/IP objects) is a follow-up (see ROADMAP P2.1); until
  then ``create`` skips with a clear reason when it lacks a ``device_type``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ..discovery.base import DiscoveredDevice, DiscoveryResult
from ..netbox.client import NetBoxClient

Action = Literal["create", "update", "delete"]

# Fields compared for update-drift. Kept to primary_ip for now — it is high-signal and
# unambiguous. site/role comparison needs a name→slug mapping layer (ROADMAP P2.1), so
# those are only included in `create` payloads, not used to trigger updates.
COMPARE_FIELDS: tuple[str, ...] = ("primary_ip",)


@dataclass
class ReconcileChange:
    """A single proposed change to NetBox."""

    action: Action
    object_type: str
    identifier: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReconcilePlan:
    """A set of proposed changes. Dry-run until explicitly applied."""

    changes: list[ReconcileChange] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    dry_run: bool = True

    @property
    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for change in self.changes:
            counts[change.action] = counts.get(change.action, 0) + 1
        return {"total": len(self.changes), "by_action": counts, "dry_run": self.dry_run}


# --- normalization helpers ------------------------------------------------------


def _name_of(value: Any) -> str | None:
    """Pull a comparable name/slug out of a NetBox FK value (dict, str, or None)."""
    if isinstance(value, dict):
        result = value.get("slug") or value.get("name") or value.get("display")
        return str(result) if result is not None else None
    if isinstance(value, str):
        return value
    return None


def _ip_of(value: Any) -> str | None:
    """Pull a bare IP (no mask) out of a NetBox primary-IP value."""
    if isinstance(value, dict):
        value = value.get("address")
    if isinstance(value, str):
        return value.split("/")[0].strip()
    return None


def _netbox_scalar(device: dict[str, Any], field_name: str) -> str | None:
    if field_name == "primary_ip":
        return _ip_of(device.get("primary_ip") or device.get("primary_ip4"))
    if field_name == "role":
        return _name_of(device.get("role") or device.get("device_role"))
    return _name_of(device.get(field_name))


def _observed_value(device: DiscoveredDevice, field_name: str) -> str | None:
    return {
        "primary_ip": device.primary_ip,
        "site": device.site,
        "role": device.role,
    }.get(field_name)


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _desired_device(device: DiscoveredDevice) -> dict[str, Any]:
    """Build the desired NetBox field set for a (possibly new) device."""
    desired: dict[str, Any] = {"name": device.name}
    if device.primary_ip:
        desired["primary_ip"] = device.primary_ip
    if device.site:
        desired["site"] = device.site
    if device.role:
        desired["role"] = device.role
    return desired


class ReconcileEngine:
    """Computes and applies the changes needed to make NetBox match reality."""

    def __init__(self, netbox: NetBoxClient | None = None) -> None:
        self.netbox = netbox

    def diff(self, observed: DiscoveryResult) -> ReconcilePlan:
        """Compare observed devices against NetBox and produce a (dry-run) plan."""
        plan = ReconcilePlan()
        netbox_devices = self.netbox.list_devices() if self.netbox else []
        by_name: dict[str, dict[str, Any]] = {
            (d.get("name") or "").lower(): d for d in netbox_devices if d.get("name")
        }

        matched: set[str] = set()
        for device in observed.devices:
            key = (device.name or "").lower()
            current = by_name.get(key)
            if current is None:
                plan.changes.append(
                    ReconcileChange(
                        action="create",
                        object_type="device",
                        identifier=device.name,
                        details=_desired_device(device),
                    )
                )
                continue
            matched.add(key)
            deltas = self._device_deltas(device, current)
            if deltas:
                plan.changes.append(
                    ReconcileChange(
                        action="update",
                        object_type="device",
                        identifier=device.name,
                        details=deltas,
                    )
                )

        stale = [by_name[k].get("name") for k in by_name if k not in matched]
        if stale:
            plan.notes.append(
                f"{len(stale)} device(s) in NetBox not seen by '{observed.collector}' "
                f"(not auto-deleted): {', '.join(str(s) for s in stale)}"
            )
        return plan

    @staticmethod
    def _device_deltas(device: DiscoveredDevice, current: dict[str, Any]) -> dict[str, Any]:
        deltas: dict[str, Any] = {}
        for field_name in COMPARE_FIELDS:
            desired = _observed_value(device, field_name)
            if desired is None:
                continue  # discovery doesn't know this field — leave NetBox alone
            existing = _netbox_scalar(current, field_name)
            if _norm(existing) != _norm(desired):
                deltas[field_name] = {"current": existing, "desired": desired}
        return deltas

    def apply(self, plan: ReconcilePlan, *, confirm: bool = False) -> dict[str, Any]:
        """Apply a plan to NetBox. No writes happen unless ``confirm`` is True."""
        if not confirm:
            return {"applied": False, "reason": "not confirmed (dry-run)", "summary": plan.summary}
        if self.netbox is None:
            return {"applied": False, "reason": "no NetBox client", "summary": plan.summary}

        results = [self._apply_change(change) for change in plan.changes]
        applied_count = sum(1 for r in results if r["status"] in ("created", "updated"))
        return {
            "applied": True,
            "applied_count": applied_count,
            "summary": plan.summary,
            "results": results,
        }

    def _apply_change(self, change: ReconcileChange) -> dict[str, Any]:
        assert self.netbox is not None  # guarded by apply()
        try:
            if change.action == "create":
                if "device_type" not in change.details:
                    return {
                        "action": "create",
                        "identifier": change.identifier,
                        "status": "skipped",
                        "detail": "device creation needs a NetBox device_type/role/site "
                        "mapping (not provided by discovery; see ROADMAP P2.1)",
                    }
                self.netbox.create_device(change.details)
                return {"action": "create", "identifier": change.identifier, "status": "created"}
            if change.action == "update":
                fields = {name: delta["desired"] for name, delta in change.details.items()}
                self.netbox.update_device(change.identifier, fields)
                return {
                    "action": "update",
                    "identifier": change.identifier,
                    "status": "updated",
                    "detail": fields,
                }
            return {
                "action": change.action,
                "identifier": change.identifier,
                "status": "skipped",
                "detail": f"unsupported action '{change.action}'",
            }
        except Exception as exc:
            return {
                "action": change.action,
                "identifier": change.identifier,
                "status": "error",
                "detail": str(exc),
            }
