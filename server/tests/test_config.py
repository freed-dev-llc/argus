"""Tests for configuration resolution."""

from __future__ import annotations

from argus.config import Settings, get_settings


def test_unconfigured_by_default():
    settings = Settings(netbox_url="", netbox_token="", _env_file=None)
    assert settings.netbox_configured is False
    assert settings.http_port == 8080


def test_configured_when_url_and_token_set(monkeypatch):
    monkeypatch.setenv("NETBOX_URL", "https://netbox.example")
    monkeypatch.setenv("NETBOX_TOKEN", "secret")
    settings = Settings(_env_file=None)
    assert settings.netbox_configured is True
    assert settings.netbox_url == "https://netbox.example"


def test_get_settings_is_cached():
    assert get_settings() is get_settings()


def test_netbox_tenant_unset_by_default():
    settings = Settings(netbox_tenant="", _env_file=None)
    assert settings.netbox_tenant == ""
    assert settings.tenant_stamping_enabled is False


def test_netbox_tenant_reads_env_and_enables_stamping(monkeypatch):
    monkeypatch.setenv("NETBOX_TENANT", "Acme")
    settings = Settings(_env_file=None)
    assert settings.netbox_tenant == "Acme"
    assert settings.tenant_stamping_enabled is True
