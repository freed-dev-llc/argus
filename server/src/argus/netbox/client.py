"""Thin ``pynetbox`` wrapper returning plain dicts (DCIM + IPAM reads)."""

from __future__ import annotations

import ipaddress
import re
from typing import Any

import pynetbox

from ..config import get_settings


def _slugify(value: str) -> str:
    """NetBox-style slug: lowercase, non-alphanumeric runs collapsed to hyphens."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "unknown"


def _with_default_mask(ip: str) -> tuple[str, int]:
    """Normalize an IP string to ``address/mask`` and return its address family.

    A mask already present in ``ip`` is honored; otherwise a family default is applied —
    ``/32`` for IPv4, ``/128`` for IPv6. Parsing uses the stdlib :mod:`ipaddress` module.

    Args:
        ip: An IP address, optionally with a prefix length (e.g. ``"10.0.0.1"`` or
            ``"2001:db8::1/64"``).

    Returns:
        A ``(address, version)`` tuple: the normalized ``address/mask`` string and the IP
        version (``4`` or ``6``).

    Raises:
        ValueError: If ``ip`` is not a valid IP address (with or without a mask).
    """
    if "/" in ip:
        interface = ipaddress.ip_interface(ip)
        return str(interface), interface.version
    address = ipaddress.ip_address(ip)
    mask = 32 if address.version == 4 else 128
    return f"{address}/{mask}", address.version


def _record(record: Any) -> dict[str, Any]:
    """Convert a pynetbox record to a plain, JSON-serializable dict."""
    data: Any = record.serialize() if hasattr(record, "serialize") else record
    return dict(data)


def _fk_name(value: Any) -> str | None:
    """Resolve a pynetbox FK (nested record) to its slug/name string."""
    if value is None:
        return None
    return getattr(value, "slug", None) or getattr(value, "name", None) or str(value) or None


def _device_to_dict(record: Any) -> dict[str, Any]:
    """Device → comparable dict with FK fields resolved to slugs/strings.

    ``record.serialize()`` flattens FKs to bare integer IDs, which can't be compared
    against discovered names — so we read the resolved attributes instead. This keeps
    the reconcile diff idempotent and gives the dashboard human-readable values.
    """
    role = getattr(record, "role", None) or getattr(record, "device_role", None)
    primary_ip = getattr(record, "primary_ip", None)
    status = getattr(record, "status", None)
    device_type = getattr(record, "device_type", None)
    manufacturer = getattr(device_type, "manufacturer", None) if device_type is not None else None
    serial = getattr(record, "serial", None)
    return {
        "id": getattr(record, "id", None),
        "name": getattr(record, "name", None),
        "status": str(status) if status else None,
        "site": _fk_name(getattr(record, "site", None)),
        "role": _fk_name(role),
        "primary_ip": str(primary_ip) if primary_ip else None,
        "device_type": _fk_name(device_type),
        "manufacturer": _fk_name(manufacturer),
        "serial": str(serial) if serial else None,
    }


class NetBoxClient:
    """Access to NetBox, the network's source of truth.

    Reads (DCIM + IPAM) plus the find-or-create / write operations the reconcile engine
    needs — `create_device`, `update_device`, `assign_primary_ip`, and the `ensure_*`
    foreign-key resolvers. Writes are driven only through the confirmation-gated reconcile
    flow (see ADR-0003).
    """

    def __init__(self, url: str, token: str, *, verify_ssl: bool = True) -> None:
        self.api = pynetbox.api(url, token=token)
        self.api.http_session.verify = verify_ssl
        # Resolved once per instance via ``_tenant_id`` (the flag caches a ``None`` result too), so
        # a multi-object apply does a single tenant find-or-create. The client is rebuilt fresh per
        # tool call, so per-instance caching is safe.
        self._tenant_resolved = False
        self._tenant_id_cache: int | None = None

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
        return [_device_to_dict(r) for r in records]

    def get_device(self, name: str) -> dict[str, Any] | None:
        """Get a single device by name, or ``None`` if not found."""
        record = self.api.dcim.devices.get(name=name)
        return _device_to_dict(record) if record else None

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
        record = self.api.dcim.devices.create(self._stamp_tenant(data))
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
        return int(
            self.api.dcim.sites.create(
                self._stamp_tenant({"name": name, "slug": slug, "status": "active"})
            ).id
        )

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

    # --- shared-instance tenant stamping (find-or-create, create-only; ADR-0007 / #86) ---------

    def ensure_tenant(self, name: str) -> int:
        """Return the id of the tenant with this name, creating it if absent (ADR-0007)."""
        slug = _slugify(name)
        existing = self.api.tenancy.tenants.get(slug=slug)
        if existing is not None:
            return int(existing.id)
        return int(self.api.tenancy.tenants.create({"name": name, "slug": slug}).id)

    def _tenant_id(self) -> int | None:
        """Resolve ``NETBOX_TENANT`` to a tenant id (find-or-create), or ``None`` when unset.

        Reads ``NETBOX_TENANT`` directly (mirroring how ``assign_primary_ip`` reads
        ``reconcile_mgmt_interface``); empty/unset → ``None``. The result is resolved once and
        cached on the instance (a ``None`` result is cached too), so a multi-object apply triggers
        a single tenant find-or-create. Invoked *only* from the create branches via
        ``_stamp_tenant`` — never from a read or ``diff`` — so a read-only drift report creates no
        tenant.
        """
        if not self._tenant_resolved:
            name = get_settings().netbox_tenant
            self._tenant_id_cache = self.ensure_tenant(name) if name else None
            self._tenant_resolved = True
        return self._tenant_id_cache

    def _stamp_tenant(self, data: dict[str, Any]) -> dict[str, Any]:
        """Stamp the configured tenant onto a create payload (no-op when ``NETBOX_TENANT`` unset).

        Create-only soft isolation (ADR-0007): applied solely on the ``ensure_*`` / ``create_*``
        create branches, never on reads or updates, so an existing object's tenant is left
        untouched. ``setdefault`` means an explicitly-provided ``tenant`` always wins, and when no
        tenant is configured the payload is returned byte-for-byte unchanged (back-compat).
        """
        tenant_id = self._tenant_id()
        if tenant_id is not None:
            data.setdefault("tenant", tenant_id)
        return data

    def ensure_ip_address(self, address: str, description: str = "") -> int:
        """Return the id of the IPAM IP (find-or-create).

        The address family is detected via the stdlib ``ipaddress`` module: a mask in the
        string is honored, otherwise ``/32`` (IPv4) or ``/128`` (IPv6) is applied.
        """
        addr, _ = _with_default_mask(address)
        existing = self.api.ipam.ip_addresses.get(address=addr)
        if existing is not None:
            return int(existing.id)
        data: dict[str, Any] = {"address": addr, "status": "active"}
        if description:
            data["description"] = description
        return int(self.api.ipam.ip_addresses.create(self._stamp_tenant(data)).id)

    def assign_primary_ip(
        self, device_name: str, ip: str, interface_name: str | None = None
    ) -> None:
        """Ensure ``device`` has ``ip`` as its primary IP (family-aware).

        Creates the management interface and the IPAM IP object (assigned to that interface)
        if they don't exist, then sets the device's ``primary_ip6`` for an IPv6 address or
        ``primary_ip4`` for IPv4. The family and mask are detected via the stdlib
        ``ipaddress`` module: a mask in the string is honored, otherwise ``/32`` (IPv4) or
        ``/128`` (IPv6) is applied. ``interface_name`` defaults to the configured
        ``RECONCILE_MGMT_INTERFACE`` (``mgmt``). Best-effort.
        """
        resolved_interface = interface_name or get_settings().reconcile_mgmt_interface

        device = self.api.dcim.devices.get(name=device_name)
        if device is None:
            raise ValueError(f"Device '{device_name}' not found in NetBox")

        interface = self.api.dcim.interfaces.get(device_id=device.id, name=resolved_interface)
        if interface is None:
            interface = self.api.dcim.interfaces.create(
                {"device": device.id, "name": resolved_interface, "type": "virtual"}
            )

        address, version = _with_default_mask(ip)
        ip_obj = self.api.ipam.ip_addresses.get(address=address)
        if ip_obj is None:
            ip_obj = self.api.ipam.ip_addresses.create(
                self._stamp_tenant(
                    {
                        "address": address,
                        "status": "active",
                        "assigned_object_type": "dcim.interface",
                        "assigned_object_id": interface.id,
                    }
                )
            )
        primary_field = "primary_ip6" if version == 6 else "primary_ip4"
        device.update({primary_field: ip_obj.id})
