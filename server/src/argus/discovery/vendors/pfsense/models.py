"""pfSense/OPNsense model-string normalization — NetBox manufacturer + role inference.

Both pfSense (Netgate-maintained) and OPNsense (community fork) are covered. In most network
topologies, these are the gateway/firewall appliance; classification by hardware model is
straightforward from vendor model strings and SNMP sysDescr.
"""

from __future__ import annotations

#: NetBox manufacturer for pfSense appliances (Netgate is the maintainer/vendor).
MANUFACTURER = "Netgate"
#: NetBox manufacturer for OPNsense (maintained by Deciso B.V.); the community fork runs on
#: white-box / VM hardware, so Deciso is the closest vendor label.
OPNSENSE_MANUFACTURER = "Deciso"


def manufacturer_from_version(version: str | None) -> str:
    """Pick the NetBox manufacturer from a firewall's version/model string.

    OPNsense identifies itself as ``OPNsense ...`` in ``show version`` / sysDescr, so a match
    on that keyword maps to Deciso; everything else (pfSense, Netgate appliances) defaults to
    Netgate. Falls back to Netgate when no version string is available (the historical default).
    """
    if version and "opnsense" in version.lower():
        return OPNSENSE_MANUFACTURER
    return MANUFACTURER

# Conservative device state → NetBox status mapping (the single source of truth).
# pfSense/OPNsense report status via SNMP sysUptime or CLI inspection; these states
# correspond to operational health. Transient states are omitted so reconcile does not
# churn existing NetBox status on partial/transient discovery.
_PFSENSE_STATE_TO_NETBOX_STATUS: dict[str, str] = {
    "up": "active",
    "down": "offline",
    "rebooting": "staged",
}


def status_from_state(state: str | None) -> str | None:
    """Map a pfSense/OPNsense device state to a NetBox status token (or None to skip).

    Case-insensitive on input; returns the lowercase NetBox status value (``"active"`` /
    ``"offline"`` / ``"staged"``) for a mapped state, and ``None`` for any unknown / transient /
    missing state so reconcile leaves NetBox's existing status untouched.
    """
    if not state:
        return None
    return _PFSENSE_STATE_TO_NETBOX_STATUS.get(state.lower())


# Match on keywords rather than exact model codes. pfSense/OPNsense run on:
# - Netgate proprietary appliances (SG-1100, SG-3100, SG-5100, SG-7100, etc.)
# - Generic x86 hardware (often in VM or white-box)
# - ARM boards (Raspberry Pi, etc.) for small deployments
# Role is almost always "gateway" (the typical use case); distinguish by model keywords.
_ROLE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gateway", ("sg-", "pfsense", "opnsense", "firewall", "gateway", "router")),
)


def role_from_model(model: str | None) -> str | None:
    """Infer a NetBox device role from a pfSense/OPNsense model string (or None).

    Nearly all pfSense/OPNsense deployments are gateways/firewalls; this classifier
    is conservative and returns 'gateway' for any recognized model, None otherwise.
    """
    if not model:
        return None
    text = model.lower()
    for role, keywords in _ROLE_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return role
    return None
