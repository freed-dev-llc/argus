"""UniFi model-string normalization — NetBox manufacturer + role inference.

The vendor-specific knowledge that used to live in the collector: the manufacturer this
pack maps to, and best-effort role inference from the UniFi Integration API's full model
names ("UniFi Dream Machine PRO SE", "USW Pro 48 PoE", "U6 Pro").
"""

from __future__ import annotations

#: NetBox manufacturer for every device this pack discovers.
MANUFACTURER = "Ubiquiti"

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
