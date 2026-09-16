import os

# OpenID Connect login for NetBox via python-social-auth (stock in NetBox 4.6).
# NetBox loads every *.py in /etc/netbox/config/ (see deploy/netbox/Dockerfile).
#
# All values come from the environment; with any of the three required keys unset
# this file defines nothing and NetBox stays on local authentication. Site values
# live in deploy/.env (gitignored); the keys are documented in .env.example.
#
# The identity provider must offer an OIDC issuer whose endpoints live under it
# (Authentik: https://<idp>/application/o/<app-slug>/). NetBox serves this behind a
# reverse proxy, so the public origin must also be in CSRF_TRUSTED_ORIGINS
# (already plumbed from NETBOX_CSRF_TRUSTED_ORIGINS in docker-compose.yml).

_oidc_client_id = os.environ.get("NETBOX_OIDC_CLIENT_ID", "").strip()
_oidc_client_secret = os.environ.get("NETBOX_OIDC_CLIENT_SECRET", "").strip()
_oidc_endpoint = os.environ.get("NETBOX_OIDC_ENDPOINT", "").strip().rstrip("/") + "/"

if _oidc_client_id and _oidc_client_secret and _oidc_endpoint:
    REMOTE_AUTH_ENABLED = True
    REMOTE_AUTH_BACKEND = "social_core.backends.open_id_connect.OpenIdConnectAuth"
    REMOTE_AUTH_AUTO_CREATE_USER = True

    # Auto-created users land in these NetBox groups (comma-separated, must already
    # exist in NetBox — group membership is what grants object permissions).
    _default_groups = os.environ.get("NETBOX_OIDC_DEFAULT_GROUPS", "")
    REMOTE_AUTH_DEFAULT_GROUPS = [g.strip() for g in _default_groups.split(",") if g.strip()]
    REMOTE_AUTH_DEFAULT_PERMISSIONS = {}

    # python-social-auth setting names derive from the backend name ("oidc").
    SOCIAL_AUTH_OIDC_OIDC_ENDPOINT = _oidc_endpoint
    SOCIAL_AUTH_OIDC_KEY = _oidc_client_id
    SOCIAL_AUTH_OIDC_SECRET = _oidc_client_secret
