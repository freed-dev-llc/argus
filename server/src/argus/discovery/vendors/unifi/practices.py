"""UniFi practices — the in-tree ruleset on the practices SPI (ADR-0009).

Read-only, advisory rules surfaced through ``evaluate_practices`` / ``GET /api/practices``. They
inspect a :class:`PracticeContext` (live observation + a read-only NetBox snapshot) and return
:class:`Finding` objects — they never write. Reconciliation (ADR-0003) remains the only writer.

``DevicesHaveRole``/``DevicesTrackedInNetBox`` show both halves of the context (observed-only and
observed+NetBox); the remaining rules are observed-only naming/coverage checks.
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


class DevicesHavePrimaryIP:
    """Every discovered device should have a primary IP (observed-only check)."""

    id = "unifi.device-has-primary-ip"
    title = "Discovered devices have a primary IP"
    severity = Severity.WARNING

    def evaluate(self, context: PracticeContext) -> list[Finding]:
        return [
            Finding(
                practice=self.id,
                severity=self.severity,
                message=f"Device {device.name!r} has no primary IP.",
                target=device.name,
                remediation="Give the device a management IP so it can be reached and reconciled.",
            )
            for device in context.observed.devices
            if not device.primary_ip
        ]


class DevicesHaveSerial:
    """Every discovered device should report a serial for asset tracking (observed-only check)."""

    id = "unifi.device-has-serial"
    title = "Discovered devices report a serial number"
    severity = Severity.INFO

    def evaluate(self, context: PracticeContext) -> list[Finding]:
        return [
            Finding(
                practice=self.id,
                severity=self.severity,
                message=f"Device {device.name!r} reports no serial number.",
                target=device.name,
                remediation="Confirm the device is fully adopted; a serial enables asset tracking.",
            )
            for device in context.observed.devices
            if device.management is None or not device.management.serial
        ]


class UniqueDeviceNames:
    """Discovered device names must be unique — reconcile keys by lowercased name (observed-only)."""

    id = "unifi.unique-device-names"
    title = "Discovered device names are unique"
    severity = Severity.ERROR

    def evaluate(self, context: PracticeContext) -> list[Finding]:
        counts: dict[str, int] = {}
        for device in context.observed.devices:
            key = (device.name or "").lower()
            counts[key] = counts.get(key, 0) + 1
        findings: list[Finding] = []
        for device in context.observed.devices:
            count = counts[(device.name or "").lower()]
            if count <= 1:
                continue
            findings.append(
                Finding(
                    practice=self.id,
                    severity=self.severity,
                    message=f"Device name {device.name!r} is shared by {count} devices.",
                    target=device.name,
                    remediation=(
                        "Give each device a unique name; reconcile keys by lowercased name "
                        "and would otherwise collide/overwrite the duplicates."
                    ),
                )
            )
        return findings


class DevicesNamed:
    """Devices should have a real name, not the collector's MAC/'unknown' fallback (observed-only)."""

    id = "unifi.device-named"
    title = "Discovered devices have a real name"
    severity = Severity.WARNING

    def evaluate(self, context: PracticeContext) -> list[Finding]:
        findings: list[Finding] = []
        for device in context.observed.devices:
            name = device.name or ""
            lowered = name.lower()
            if name and lowered != "unknown" and lowered != (device.mac or "").lower():
                continue  # a real name — not a fallback
            findings.append(
                Finding(
                    practice=self.id,
                    severity=self.severity,
                    message=f"Device {device.name!r} has no real name (fell back to MAC/'unknown').",
                    target=device.name,
                    remediation="Name the device in the UniFi controller so discovery reports it.",
                )
            )
        return findings


#: The practices this pack ships (wired onto UNIFI_PACK).
UNIFI_PRACTICES = (
    DevicesHaveRole(),
    DevicesTrackedInNetBox(),
    DevicesHavePrimaryIP(),
    DevicesHaveSerial(),
    UniqueDeviceNames(),
    DevicesNamed(),
)
