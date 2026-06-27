"""Application settings, resolved from environment variables (and an optional .env)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Argus runtime configuration.

    Environment variables are matched case-insensitively, so ``NETBOX_URL`` maps to
    :attr:`netbox_url`. A local ``.env`` file is read if present.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # NetBox (the source of truth)
    netbox_url: str = ""
    netbox_token: str = ""
    netbox_verify_ssl: bool = True

    # UniFi Network controller (discovery collector — Integration API, X-API-KEY)
    unifi_url: str = ""
    unifi_api_token: str = ""
    unifi_site: str = "default"
    unifi_verify_ssl: bool = False  # UniFi controllers use self-signed certs

    # SNMP/LLDP collector (generic, for non-UniFi gear). Comma-separated host[:community].
    snmp_targets: str = ""
    snmp_community: str = "public"

    # FastAPI HTTP server
    http_host: str = "0.0.0.0"
    http_port: int = 8080
    http_token: str = ""  # optional static bearer token; unset disables auth
    netbox_webhook_secret: str = ""  # HMAC secret for NetBox X-Hook-Signature; unset disables

    # Scheduled discovery + drift alerting (in-process asyncio loop; opt-in)
    schedule_interval: int = 0  # seconds between drift cycles; 0 disables (e.g. 300 = 5 min)
    schedule_collector: str = "unifi"  # collector the scheduled drift cycle observes
    alert_webhook_url: str = ""  # Slack-compatible webhook; alert fires only on drift when set

    # Webhook reactions (opt-in): an authenticated NetBox webhook for an allow-listed model
    # triggers one read-only drift cycle (discovery + diff; never a write). Off by default.
    webhook_reactions_enabled: bool = False
    webhook_reaction_models: str = "dcim.device,ipam.ipaddress"  # comma-separated allow-list

    # Mnemosyne knowledge brain (RAG): base URL of a mnemosyne-http service. Powers the
    # dashboard "Ask the Brain" feature — Argus discovers the network, Mnemosyne explains it.
    # Empty disables the feature.
    mnemosyne_url: str = ""

    @property
    def http_auth_enabled(self) -> bool:
        """True when a static bearer token is configured for the HTTP API."""
        return bool(self.http_token)

    @property
    def webhook_verification_enabled(self) -> bool:
        """True when a NetBox webhook HMAC secret is configured (X-Hook-Signature)."""
        return bool(self.netbox_webhook_secret)

    @property
    def schedule_enabled(self) -> bool:
        """True when the scheduled drift loop is enabled (a positive interval is set)."""
        return self.schedule_interval > 0

    @property
    def reactions_enabled(self) -> bool:
        """True when opt-in, event-triggered read-only drift reactions are enabled."""
        return self.webhook_reactions_enabled

    @property
    def netbox_configured(self) -> bool:
        """True when both a NetBox URL and token are set."""
        return bool(self.netbox_url and self.netbox_token)

    @property
    def mnemosyne_configured(self) -> bool:
        """True when a Mnemosyne knowledge-brain URL is set."""
        return bool(self.mnemosyne_url)

    @property
    def unifi_configured(self) -> bool:
        """True when both a UniFi URL and API token are set."""
        return bool(self.unifi_url and self.unifi_api_token)


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
