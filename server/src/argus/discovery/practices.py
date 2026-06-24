"""Vendor-pack practices SPI — best-practice / validation rules (ADR-0009).

A *practice* is a read-only, advisory rule a vendor pack ships to validate how a network is
set up and how it should be modeled in NetBox. Practices are evaluated against a
:class:`PracticeContext` that carries **both** the live observation (``observed``) and a
read-only snapshot of NetBox (``netbox_devices``), and they return :class:`Finding` objects.
Practices never mutate anything — reconciliation (ADR-0003) remains the only writer.

A pack declares its rules on :attr:`~argus.discovery.vendors.pack.VendorPack.practices`; the
``evaluate_practices`` tool runs them and returns the findings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from .base import DiscoveryResult


class Severity(StrEnum):
    """How serious a practice finding is."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Finding:
    """A single practice result — one thing a pack thinks is worth flagging."""

    practice: str  # the Practice.id that produced this finding
    severity: Severity
    message: str
    target: str | None = None  # what it's about, e.g. a device name
    remediation: str | None = None


@dataclass
class PracticeContext:
    """Everything a practice may inspect: live observation + a NetBox snapshot.

    ``netbox_devices`` is a read-only snapshot (empty when NetBox is unconfigured;
    ``netbox_available`` says which, so a practice can no-op rather than emit false findings).
    Practices are read-only — to act on a finding, use the reconcile tools, which remain the
    sole writer into NetBox.
    """

    observed: DiscoveryResult
    netbox_devices: list[dict[str, Any]] = field(default_factory=list)
    netbox_available: bool = False


@runtime_checkable
class Practice(Protocol):
    """A best-practice / validation rule a vendor pack ships (ADR-0009).

    Implementations are small, self-describing objects: a stable ``id``, a human ``title``, a
    default ``severity``, and an ``evaluate`` that inspects the context and returns findings
    (an empty list means the practice passed).
    """

    id: str
    title: str
    severity: Severity

    def evaluate(self, context: PracticeContext) -> list[Finding]: ...
