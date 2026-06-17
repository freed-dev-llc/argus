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

    # FastAPI HTTP server
    http_host: str = "0.0.0.0"
    http_port: int = 8080

    @property
    def netbox_configured(self) -> bool:
        """True when both a NetBox URL and token are set."""
        return bool(self.netbox_url and self.netbox_token)


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
