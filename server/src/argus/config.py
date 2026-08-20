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
    unifi_site: str = "default"  # site internalReference; empty / "*" / "all" → discover all sites
    unifi_verify_ssl: bool = False  # UniFi controllers use self-signed certs

    # Docker workload discovery (ADR-0015). "name=target" pairs, comma-separated:
    #   cerebrum=cerebrum,thor=thor,helios=root@10.0.0.9,spark=local
    # target is any SSH destination; "local" runs without SSH (the host Argus is on).
    docker_hosts: str = ""
    # Per-host docker binary overrides, same shape. QNAP's Container Station keeps the
    # binary off PATH, so a fleet needs per-host paths:
    #   thor=/share/ZFS530_DATA/.qpkg/container-station/bin/docker
    docker_binaries: str = ""
    docker_ssh_timeout: int = 10  # SSH connect timeout per host, seconds

    # SNMP/LLDP collector (generic, for non-UniFi gear). Comma-separated host[:community].
    snmp_targets: str = ""
    snmp_community: str = "public"
    snmp_port: int = 161
    snmp_timeout: float = 1.0  # per-request seconds (pysnmp default)
    snmp_retries: int = 5  # pysnmp default
    # SNMPv3 (global; setting SNMP_V3_USER switches every target to v3).
    snmp_v3_user: str = ""
    snmp_v3_auth_key: str = ""
    snmp_v3_auth_protocol: str = "sha"  # md5|sha|sha224|sha256|sha384|sha512
    snmp_v3_priv_key: str = ""
    snmp_v3_priv_protocol: str = "aes128"  # des|aes128|aes192|aes256

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

    # Reconcile (NetBox write path): management interface a primary IP is assigned to.
    reconcile_mgmt_interface: str = "mgmt"

    # Shared-instance soft isolation (ADR-0007): find-or-create this NetBox tenant and stamp it on
    # the objects the confirmation-gated reconcile *creates* (devices, IP addresses, and the sites
    # it auto-creates). Create-only — an existing object's tenant is never touched. Unset (default)
    # = single-tenant, byte-for-byte unchanged. Soft only: shared catalog objects, components, and
    # cables carry no tenant, so this is a label, not true isolation (#86).
    netbox_tenant: str = ""

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
    def tenant_stamping_enabled(self) -> bool:
        """True when a NetBox tenant is configured for shared-instance create-stamping (#86)."""
        return bool(self.netbox_tenant)

    @property
    def mnemosyne_configured(self) -> bool:
        """True when a Mnemosyne knowledge-brain URL is set."""
        return bool(self.mnemosyne_url)

    @property
    def docker_configured(self) -> bool:
        """True when at least one Docker host is configured."""
        return bool(self.docker_hosts.strip())

    @property
    def unifi_configured(self) -> bool:
        """True when both a UniFi URL and API token are set."""
        return bool(self.unifi_url and self.unifi_api_token)

    @property
    def snmp_v3_enabled(self) -> bool:
        """True when an SNMPv3 user is set (every SNMP target then uses v3 USM)."""
        return bool(self.snmp_v3_user)


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
