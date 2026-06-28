"""UniFi model-string normalization — NetBox manufacturer + role inference.

The vendor-specific knowledge that used to live in the collector: the manufacturer this
pack maps to, and best-effort role inference from the UniFi Integration API's full model
names ("UniFi Dream Machine PRO SE", "USW Pro 48 PoE", "U6 Pro").
"""

from __future__ import annotations

#: NetBox manufacturer for every device this pack discovers.
MANUFACTURER = "Ubiquiti"

# Conservative UniFi-state → NetBox-status mapping (the single source of truth; see the note
# appended to ADR-0010). Only states with an unambiguous NetBox meaning are mapped; every other,
# unknown, or transient state (UPDATING / PROVISIONING / GETTING_READY / …) is deliberately
# absent so ``status_from_state`` returns ``None`` and reconcile skips it — a sparse or transient
# discovery run never blanks out or churns the device status NetBox already holds.
_UNIFI_STATE_TO_NETBOX_STATUS: dict[str, str] = {
    "ONLINE": "active",
    "OFFLINE": "offline",
    "PENDING_ADOPTION": "staged",
    "ADOPTING": "staged",
}


def status_from_state(state: str | None) -> str | None:
    """Map a UniFi device ``state`` to a NetBox status token (or ``None`` to skip).

    Case-insensitive on input; returns the lowercase NetBox status value (``"active"`` /
    ``"offline"`` / ``"staged"``) for a mapped state, and ``None`` for any unknown / transient /
    missing state so reconcile leaves NetBox's existing status untouched.
    """
    if not state:
        return None
    return _UNIFI_STATE_TO_NETBOX_STATUS.get(state.upper())


# Match on keywords rather than code prefixes (the API returns full model names). Order
# matters — gateway is checked first.
_ROLE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gateway", ("dream machine", "udm", "uxg", "ucg", "ugw", "cloud gateway", "security gateway", "gateway")),
    ("switch", ("usw", "switch", "aggregation", "us-")),
    ("ap", ("u6", "u7", "uap", "access point", "nanohd", "ac lite", "ac pro", "ac mesh")),
)


def role_from_model(model: str | None) -> str | None:
    """Infer a NetBox device role from a UniFi model string (or ``None``)."""
    if not model:
        return None
    text = model.lower()
    for role, keywords in _ROLE_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return role
    return None
