"""Vendor model normalization — replace with your vendor's manufacturer + role mapping."""

from __future__ import annotations

#: The NetBox manufacturer your devices map to.
MANUFACTURER = "Example Networks"

# Best-effort NetBox device-role inference from a model string. Order matters.
_ROLE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gateway", ("gateway", "router", "firewall")),
    ("switch", ("switch", "sw")),
    ("ap", ("ap", "access point", "wifi")),
)


def role_from_model(model: str | None) -> str | None:
    if not model:
        return None
    text = model.lower()
    for role, keywords in _ROLE_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return role
    return None
