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

    @property
    def http_auth_enabled(self) -> bool:
        """True when a static bearer token is configured for the HTTP API."""
        return bool(self.http_token)

    @property
    def netbox_configured(self) -> bool:
        """True when both a NetBox URL and token are set."""
        return bool(self.netbox_url and self.netbox_token)

    @property
    def unifi_configured(self) -> bool:
        """True when both a UniFi URL and API token are set."""
        return bool(self.unifi_url and self.unifi_api_token)


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
