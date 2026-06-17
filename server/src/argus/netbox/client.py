"""Thin ``pynetbox`` wrapper returning plain dicts (DCIM + IPAM reads)."""

from __future__ import annotations

import re
from typing import Any

import pynetbox


def _slugify(value: str) -> str:
    """NetBox-style slug: lowercase, non-alphanumeric runs collapsed to hyphens."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "unknown"


def _record(record: Any) -> dict[str, Any]:
    """Convert a pynetbox record to a plain, JSON-serializable dict."""
    data: Any = record.serialize() if hasattr(record, "serialize") else record
    return dict(data)


class NetBoxClient:
    """Read access to NetBox, the network's source of truth.

    Only reads are implemented today; reconciliation writes will be added alongside the
    reconcile engine (see ADR-0003).
    """

    def __init__(self, url: str, token: str, *, verify_ssl: bool = True) -> None:
        self.api = pynetbox.api(url, token=token)
        self.api.http_session.verify = verify_ssl

    def list_devices(
        self, site: str | None = None, role: str | None = None
    ) -> list[dict[str, Any]]:
        """List DCIM devices, optionally filtered by site and/or role slug."""
        filters: dict[str, str] = {}
        if site:
            filters["site"] = site
        if role:
            filters["role"] = role
        records = (
            self.api.dcim.devices.filter(**filters)
            if filters
            else self.api.dcim.devices.all()
        )
        return [_record(r) for r in records]

    def get_device(self, name: str) -> dict[str, Any] | None:
        """Get a single device by name, or ``None`` if not found."""
        record = self.api.dcim.devices.get(name=name)
        return _record(record) if record else None

    def list_prefixes(self) -> list[dict[str, Any]]:
        """List IPAM prefixes."""
        return [_record(r) for r in self.api.ipam.prefixes.all()]

    def list_ip_addresses(self, prefix: str | None = None) -> list[dict[str, Any]]:
        """List IPAM IP addresses, optionally scoped to a parent prefix (CIDR)."""
        records = (
            self.api.ipam.ip_addresses.filter(parent=prefix)
            if prefix
            else self.api.ipam.ip_addresses.all()
        )
        return [_record(r) for r in records]

    def search(self, query: str) -> dict[str, list[dict[str, Any]]]:
        """Free-text search across devices and IP addresses."""
        return {
            "devices": [_record(r) for r in self.api.dcim.devices.filter(q=query)],
            "ip_addresses": [_record(r) for r in self.api.ipam.ip_addresses.filter(q=query)],
        }

    # --- writes (used by the reconcile engine) ---------------------------------

    def create_device(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a device in NetBox.

        ``data`` must satisfy NetBox's required fields (notably ``device_type``,
        ``role``, and ``site``). Raises whatever pynetbox raises on validation failure.
        """
        record = self.api.dcim.devices.create(data)
        return _record(record)

    def update_device(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update fields on an existing device, matched by name."""
        record = self.api.dcim.devices.get(name=name)
        if record is None:
            raise ValueError(f"Device '{name}' not found in NetBox")
        record.update(data)
        return _record(record)

    # --- foreign-key resolution (find-or-create) -------------------------------

    def ensure_site(self, name: str) -> int:
        """Return the id of the site with this name, creating it if absent."""
        slug = _slugify(name)
        existing = self.api.dcim.sites.get(slug=slug)
        if existing is not None:
            return int(existing.id)
        return int(self.api.dcim.sites.create({"name": name, "slug": slug, "status": "active"}).id)

    def ensure_role(self, name: str) -> int:
        """Return the id of the device role with this name, creating it if absent."""
        slug = _slugify(name)
        existing = self.api.dcim.device_roles.get(slug=slug)
        if existing is not None:
            return int(existing.id)
        created = self.api.dcim.device_roles.create(
            {"name": name, "slug": slug, "color": "9e9e9e"}
        )
        return int(created.id)

    def ensure_manufacturer(self, name: str) -> int:
        """Return the id of the manufacturer with this name, creating it if absent."""
        slug = _slugify(name)
        existing = self.api.dcim.manufacturers.get(slug=slug)
        if existing is not None:
            return int(existing.id)
        return int(self.api.dcim.manufacturers.create({"name": name, "slug": slug}).id)

    def ensure_device_type(self, model: str, manufacturer_id: int) -> int:
        """Return the id of the device type for this model, creating it if absent."""
        slug = _slugify(model)
        existing = self.api.dcim.device_types.get(slug=slug)
        if existing is not None:
            return int(existing.id)
        created = self.api.dcim.device_types.create(
            {"model": model, "slug": slug, "manufacturer": manufacturer_id}
        )
        return int(created.id)

    def ensure_ip_address(self, address: str, description: str = "") -> int:
        """Return the id of the IPAM IP (find-or-create). Assumes /32 when no mask given."""
        addr = address if "/" in address else f"{address}/32"
        existing = self.api.ipam.ip_addresses.get(address=addr)
        if existing is not None:
            return int(existing.id)
        data: dict[str, Any] = {"address": addr, "status": "active"}
        if description:
            data["description"] = description
        return int(self.api.ipam.ip_addresses.create(data).id)

    def assign_primary_ip(self, device_name: str, ip: str, interface_name: str = "mgmt") -> None:
        """Ensure ``device`` has ``ip`` as its primary IPv4.

        Creates a management interface and the IPAM IP object (assigned to that interface)
        if they don't exist, then sets the device's ``primary_ip4``. Assumes /32 when no
        mask is given. Best-effort, IPv4 only.
        """
        device = self.api.dcim.devices.get(name=device_name)
        if device is None:
            raise ValueError(f"Device '{device_name}' not found in NetBox")

        interface = self.api.dcim.interfaces.get(device_id=device.id, name=interface_name)
        if interface is None:
            interface = self.api.dcim.interfaces.create(
                {"device": device.id, "name": interface_name, "type": "virtual"}
            )

        address = ip if "/" in ip else f"{ip}/32"
        ip_obj = self.api.ipam.ip_addresses.get(address=address)
        if ip_obj is None:
            ip_obj = self.api.ipam.ip_addresses.create(
                {
                    "address": address,
                    "status": "active",
                    "assigned_object_type": "dcim.interface",
                    "assigned_object_id": interface.id,
                }
            )
        device.update({"primary_ip4": ip_obj.id})
