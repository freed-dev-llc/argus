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

# Fields compared for update-drift. Resolved to NetBox foreign keys on apply.
COMPARE_FIELDS: tuple[str, ...] = ("primary_ip", "site", "role")


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
    if device.model:
        desired["model"] = device.model
    if device.manufacturer:
        desired["manufacturer"] = device.manufacturer
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

        # Client IP/MAC bindings → IPAM: propose creating IPs NetBox doesn't have yet.
        if observed.clients:
            existing_ips = {
                _ip_of(d.get("address"))
                for d in (self.netbox.list_ip_addresses() if self.netbox else [])
            }
            existing_ips.discard(None)
            seen_ips: set[str] = set()
            for client in observed.clients:
                if not client.ip:
                    continue
                ip = client.ip.split("/")[0]
                if ip in seen_ips or ip in existing_ips:
                    continue
                seen_ips.add(ip)
                plan.changes.append(
                    ReconcileChange(
                        action="create",
                        object_type="ip_address",
                        identifier=ip,
                        details={"address": ip, "description": client.hostname or ""},
                    )
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
        try:
            if change.action == "create":
                if change.object_type == "ip_address":
                    return self._create_ip(change)
                return self._create_device(change)
            if change.action == "update":
                return self._update_device(change)
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

    def _create_device(self, change: ReconcileChange) -> dict[str, Any]:
        """Resolve foreign keys (creating supporting objects as needed) and create the device."""
        nb = self.netbox
        assert nb is not None
        details = change.details
        if not (details.get("site") and details.get("role") and details.get("model")):
            return {
                "action": "create",
                "identifier": change.identifier,
                "status": "skipped",
                "detail": "create needs site, role, and model to resolve the NetBox "
                "site / role / device_type",
            }
        manufacturer_id = nb.ensure_manufacturer(details.get("manufacturer") or "Unknown")
        nb.create_device(
            {
                "name": details["name"],
                "device_type": nb.ensure_device_type(details["model"], manufacturer_id),
                "role": nb.ensure_role(details["role"]),
                "site": nb.ensure_site(details["site"]),
                "status": "active",
            }
        )
        if details.get("primary_ip"):
            nb.assign_primary_ip(details["name"], details["primary_ip"])
        return {"action": "create", "identifier": change.identifier, "status": "created"}

    def _create_ip(self, change: ReconcileChange) -> dict[str, Any]:
        """Create an IPAM IP address from a discovered client binding."""
        nb = self.netbox
        assert nb is not None
        nb.ensure_ip_address(change.details["address"], change.details.get("description") or "")
        return {
            "action": "create",
            "identifier": change.identifier,
            "status": "created",
            "detail": "ip_address",
        }

    def _update_device(self, change: ReconcileChange) -> dict[str, Any]:
        """Resolve and apply field deltas to an existing device."""
        nb = self.netbox
        assert nb is not None
        fields: dict[str, Any] = {}
        primary_ip: str | None = None
        for field_name, delta in change.details.items():
            desired = delta["desired"]
            if field_name == "site":
                fields["site"] = nb.ensure_site(desired)
            elif field_name == "role":
                fields["role"] = nb.ensure_role(desired)
            elif field_name == "primary_ip":
                primary_ip = desired
        if fields:
            nb.update_device(change.identifier, fields)
        if primary_ip:
            nb.assign_primary_ip(change.identifier, primary_ip)
        applied = dict(fields)
        if primary_ip:
            applied["primary_ip"] = primary_ip
        return {
            "action": "update",
            "identifier": change.identifier,
            "status": "updated",
            "detail": applied,
        }
