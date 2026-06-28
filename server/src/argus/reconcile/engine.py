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
from ..netbox.client import NetBoxClient, _slugify

Action = Literal["create", "update", "delete"]

# Fields compared for update-drift. Resolved to NetBox foreign keys on apply. ``device_type``
# and ``manufacturer`` jointly resolve to the NetBox device_type FK (see ``_update_device``);
# ``serial`` is a plain device field (ADR-0010 management-plane write-back).
COMPARE_FIELDS: tuple[str, ...] = (
    "primary_ip",
    "site",
    "role",
    "device_type",
    "manufacturer",
    "serial",
)

# Fields whose observed (free-text) value is compared slug-normalized against NetBox's slug.
_SLUG_COMPARE_FIELDS: frozenset[str] = frozenset({"device_type", "manufacturer"})


@dataclass(frozen=True)
class DeviceTypeIntent:
    """Apply-only data to resolve a device_type FK from the observed (model, manufacturer).

    Carried on a :class:`ReconcileChange` separately from ``details`` so the drift report shows
    only genuinely-drifted fields — never the non-drifted half of the model/manufacturer pair.
    """

    model: str
    manufacturer: str | None = None


@dataclass
class ReconcileChange:
    """A single proposed change to NetBox."""

    action: Action
    object_type: str
    identifier: str
    details: dict[str, Any] = field(default_factory=dict)
    # Apply-only: the observed (model, manufacturer) to resolve into the device_type FK. Not
    # surfaced by the drift report (``_change_dict`` serializes only ``details``), so reported
    # deltas stay limited to real drift while apply still resolves under the real manufacturer.
    device_type_resolution: DeviceTypeIntent | None = None


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
        "device_type": device.model,
        "manufacturer": device.manufacturer,
        # Management-plane facts live under device.management (ADR-0010), not top-level.
        "serial": device.management.serial if device.management else None,
    }.get(field_name)


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _compare_key(field_name: str, value: str | None) -> str:
    """Normalize a field value for drift comparison.

    ``device_type``/``manufacturer`` compare slug-normalized: observed values are free-text but
    NetBox stores slugs, so slugifying both sides keeps an argus-created device (whose
    device_type slug came from ``ensure_device_type(model)``) from showing phantom drift. Other
    fields keep the existing case-insensitive ``_norm`` comparison.
    """
    if field_name in _SLUG_COMPARE_FIELDS:
        return _slugify(value) if value else ""
    return _norm(value)


def _device_type_intent(
    device: DiscoveredDevice, deltas: dict[str, Any]
) -> DeviceTypeIntent | None:
    """Return the apply-only device_type resolution when device_type/manufacturer drifts.

    ``device_type`` and ``manufacturer`` jointly resolve to a single NetBox device_type FK on
    apply (``ensure_device_type(model, ensure_manufacturer(mfr))``), which needs *both* observed
    values — but a per-field diff only reports the field(s) that actually drifted. So when either
    drifts, return the full observed pair for apply, kept off the reported ``deltas`` so the drift
    report never shows the non-drifted (e.g. case-only / no-op) half as drift.

    Returns ``None`` when neither field drifted, or when there is no observed ``model`` — a
    manufacturer has no standalone NetBox field, so without a model the drift is unresolvable.
    """
    if "device_type" not in deltas and "manufacturer" not in deltas:
        return None
    if device.model is None:
        return None
    return DeviceTypeIntent(model=device.model, manufacturer=device.manufacturer)


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
            deltas, dt_intent = self._device_deltas(device, current)
            if deltas:
                plan.changes.append(
                    ReconcileChange(
                        action="update",
                        object_type="device",
                        identifier=device.name,
                        details=deltas,
                        device_type_resolution=dt_intent,
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
    def _device_deltas(
        device: DiscoveredDevice, current: dict[str, Any]
    ) -> tuple[dict[str, Any], DeviceTypeIntent | None]:
        """Return (reported deltas of genuinely-drifted fields, apply-only device_type intent)."""
        deltas: dict[str, Any] = {}
        for field_name in COMPARE_FIELDS:
            desired = _observed_value(device, field_name)
            if desired is None:
                continue  # discovery doesn't know this field — leave NetBox alone
            existing = _netbox_scalar(current, field_name)
            if _compare_key(field_name, existing) != _compare_key(field_name, desired):
                deltas[field_name] = {"current": existing, "desired": desired}
        return deltas, _device_type_intent(device, deltas)

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
            elif field_name == "serial":
                fields["serial"] = desired  # plain device field (ADR-0010 write-back)
        # device_type + manufacturer drift jointly resolve to one device_type FK, carried as an
        # apply-only intent (off the reported deltas) so it resolves under the real manufacturer.
        intent = change.device_type_resolution
        if intent is not None:
            mfr_id = nb.ensure_manufacturer(intent.manufacturer or "Unknown")
            fields["device_type"] = nb.ensure_device_type(intent.model, mfr_id)
        if not fields and primary_ip is None:
            # Nothing resolvable to write (e.g. manufacturer drift with no observed model —
            # manufacturer has no standalone NetBox field). Report it honestly, not as a success.
            return {
                "action": "update",
                "identifier": change.identifier,
                "status": "skipped",
                "detail": "no resolvable NetBox field to write for the observed drift",
            }
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
