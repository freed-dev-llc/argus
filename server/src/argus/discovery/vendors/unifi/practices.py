"""UniFi practices — the in-tree worked example of the practices SPI (ADR-0009).

Two small rules that together show both halves of a :class:`PracticeContext`: one reads only
the live observation, the other cross-references the NetBox snapshot.
"""

from __future__ import annotations

from ...practices import Finding, PracticeContext, Severity


class DevicesHaveRole:
    """Every discovered device should resolve to a NetBox role (observed-only check)."""

    id = "unifi.device-has-role"
    title = "Discovered devices resolve to a NetBox role"
    severity = Severity.WARNING

    def evaluate(self, context: PracticeContext) -> list[Finding]:
        return [
            Finding(
                practice=self.id,
                severity=self.severity,
                message=f"Device {device.name!r} has no role (model {device.model!r} unrecognized).",
                target=device.name,
                remediation="Extend the pack's role_from_model(), or set the role in NetBox.",
            )
            for device in context.observed.devices
            if not device.role
        ]


class DevicesTrackedInNetBox:
    """Every discovered device should already exist in NetBox (uses observed + NetBox)."""

    id = "unifi.device-in-netbox"
    title = "Discovered devices are tracked in NetBox"
    severity = Severity.INFO

    def evaluate(self, context: PracticeContext) -> list[Finding]:
        if not context.netbox_available:
            return []  # no NetBox snapshot — can't tell, so stay silent
        known = {(d.get("name") or "").lower() for d in context.netbox_devices}
        return [
            Finding(
                practice=self.id,
                severity=self.severity,
                message=f"Device {device.name!r} is observed but not yet in NetBox.",
                target=device.name,
                remediation="Run reconcile_apply to add it to the source of truth.",
            )
            for device in context.observed.devices
            if (device.name or "").lower() not in known
        ]


#: The practices this pack ships (wired onto UNIFI_PACK).
UNIFI_PRACTICES = (DevicesHaveRole(), DevicesTrackedInNetBox())
