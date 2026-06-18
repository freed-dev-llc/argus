"""Parse and classify inbound NetBox webhook events for observability.

NetBox 4.x POSTs a JSON change event to ``/webhooks/netbox`` whenever a configured object
is created, updated, or deleted. This module turns that payload into a small, structured
:class:`NetBoxEvent` for logging and acking. It is **observability only** — it never
triggers discovery, reconcile, or any NetBox write (reactions are a later phase).

Parsing is total and defensive: a non-``Mapping`` payload, or any missing/null/oddly-typed
field, yields ``None`` for that field and never raises, so a malformed webhook cannot crash
the handler.

Known gap: this does not verify NetBox's ``X-Hook-Signature`` HMAC. Webhook authenticity
currently relies on the HTTP bearer token (``HTTP_TOKEN``); signature verification is future
hardening.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any


def _scalar(value: Any) -> str | int | None:
    """Return ``value`` if it is a plain ``str``/``int``, else ``None`` (never raises)."""
    return value if isinstance(value, str | int) else None


@dataclass(frozen=True)
class NetBoxEvent:
    """A classified NetBox webhook change event (observability fields only)."""

    event: str | int | None = None
    model: str | int | None = None
    object_id: str | int | None = None
    display: str | int | None = None
    username: str | int | None = None
    request_id: str | int | None = None
    timestamp: str | int | None = None

    def summary(self) -> str:
        """Return a compact, greppable one-line description for human logs."""
        object_ref = self.object_id if self.object_id is not None else "?"
        return (
            f"{self.event or '?'} {self.model or '?'} #{object_ref} "
            f"({self.display or '?'}) by {self.username or '?'}"
        )

    def log_fields(self) -> dict[str, Any]:
        """Return the structured fields for the log record / ack body.

        Deliberately excludes the full ``data`` / ``snapshots`` blobs — only the
        classified scalar fields are surfaced.
        """
        return asdict(self)

    def as_dict(self) -> dict[str, Any]:
        """Return the classified fields as a plain dict (alias of :meth:`log_fields`)."""
        return asdict(self)


def parse_netbox_event(payload: Mapping[str, Any]) -> NetBoxEvent:
    """Classify a NetBox webhook payload into a :class:`NetBoxEvent`.

    Total and defensive: a non-``Mapping`` payload, or any missing/null/oddly-typed field,
    yields ``None`` for that field. Never raises.

    Args:
        payload: The decoded JSON body of a NetBox webhook POST.

    Returns:
        A :class:`NetBoxEvent` carrying whatever fields could be safely extracted.
    """
    if not isinstance(payload, Mapping):
        return NetBoxEvent()
    data = payload.get("data")
    if not isinstance(data, Mapping):
        data = {}
    display = data.get("display")
    if display is None:
        display = data.get("name")
    return NetBoxEvent(
        event=_scalar(payload.get("event")),
        model=_scalar(payload.get("model")),
        object_id=_scalar(data.get("id")),
        display=_scalar(display),
        username=_scalar(payload.get("username")),
        request_id=_scalar(payload.get("request_id")),
        timestamp=_scalar(payload.get("timestamp")),
    )
