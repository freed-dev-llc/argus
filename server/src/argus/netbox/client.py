"""Thin ``pynetbox`` wrapper returning plain dicts (DCIM + IPAM reads)."""

from __future__ import annotations

from typing import Any

import pynetbox


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
