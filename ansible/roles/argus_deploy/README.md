# Role: `argus_deploy`

Deploys the self-contained Argus stack (NetBox + its datastore + Argus server + web) to a
Docker host, replacing the manual rsync / secret-generation / `docker compose up` steps.

What it does:

1. (Optional) `git` the Argus repo to `argus_dest` (`argus_manage_repo: true`).
2. Render `deploy/.env`. **Secrets are generated once and reused** from the existing `.env`
   on subsequent runs (NetBox secret key, DB password, superuser password, API token, and the
   API token pepper), so re-running never rotates them. Optional values that have a role
   variable (`HTTP_TOKEN`, the bind addresses, the OIDC keys, the `SCHEDULE_*` pair, and so
   on) are read back from the existing file when the variable is blank. **Every other key in
   the existing file is carried over verbatim** (NetBird, firewall, and Docker collector
   settings, `ARGUS_SSH_DIR`, anything added by hand), so a re-run never drops a
   host-specific setting.
3. `docker compose up` (build + start) via `community.docker.docker_compose_v2`; a `.env`
   change triggers a recreate handler. Set `argus_manage_stack: false` to render `.env` and
   stop there.

## Requirements

- Control node: `community.docker` collection (see `../requirements.yml`).
- Target: Docker + the `docker compose` v2 CLI (Docker Desktop / OrbStack / Docker Engine).

## Key variables (see `defaults/main.yml`)

| Variable | Default | Notes |
| --- | --- | --- |
| `argus_dest` | `~/argus` | Where the repo lives on the target. |
| `argus_manage_repo` | `true` | `false` = use an already-present checkout. |
| `argus_version` | `main` | Git ref to deploy. |
| `argus_netbox_image` | `netboxcommunity/netbox:v4.6-5.0.1` | NetBox image pin. |
| `argus_unifi_url` / `argus_unifi_api_token` | `""` | Set via Vault; blank reuses the target's existing `.env`. |
| `argus_netbox_csrf_trusted_origins` | `""` | Trusted https origin(s) for NetBox CSRF when served over HTTPS behind a proxy/tunnel; blank reuses existing `.env`. |
| `argus_http_token` | `""` | Bearer token enforced on `/api` + `/webhooks`; blank = open. Blank reuses existing `.env`. |
| `argus_netbox_webhook_secret` | `""` | NetBox webhook HMAC secret — verifies `X-Hook-Signature` on `/webhooks/netbox` (server-only); blank = off. Blank reuses existing `.env`. |
| `argus_schedule_interval` / `argus_schedule_collector` | `""` | In-process drift schedule (seconds / collector). Blank reuses existing `.env` (compose defaults `0` / `unifi`). |
| `argus_alert_webhook_url` | `""` | Slack-compatible webhook; POSTs on drift when set. Blank reuses existing `.env`. |
| `argus_netbox_bind` / `argus_web_bind` | `""` | Bind address for the NetBox UI (`:8096`) and the dashboard (`:8095`); a mesh address keeps them off the LAN (pair with `deploy/argus.service`). Blank reuses existing `.env`; compose defaults to `0.0.0.0`. |
| `argus_netbox_oidc_client_id` / `_client_secret` / `_endpoint` / `_default_groups` | `""` | NetBox OIDC remote auth (Authentik or any issuer); with any of the three required keys unset NetBox stays on local auth. Blank reuses existing `.env`. |
| `argus_manage_stack` | `true` | `false` renders `deploy/.env` only: no `compose up`, no recreate handler. |
| `argus_docker_path` | macOS OrbStack/Homebrew + system paths | PATH so the module finds `docker`. |

## Usage

```bash
cd ansible
ansible-galaxy collection install -r requirements.yml
cp inventory/hosts.example.yml inventory/hosts.yml   # edit
ansible-playbook deploy-argus.yml                     # hosts.yml is a default inventory source
```

Idempotent: a second run with no config change makes no changes (secrets are reused).

## Render check

`playbooks/argus-env-render-check.yml` runs the role against a scratch directory on
localhost with `argus_manage_stack: false`. It seeds an existing `.env` with a secret and
unmanaged keys, then asserts that the secret is reused, the unmanaged keys survive, and every
generated secret (including the token pepper) is present. Run it after any change to
`tasks/env.yml` or `templates/env.j2`:

```bash
cd ansible
ansible-playbook -i localhost, playbooks/argus-env-render-check.yml
```

`server/tests/test_ansible_env_role.py` is the offline counterpart: it checks that every key
the role manages exists in `deploy/.env.example`, that the security-relevant keys are managed
explicitly, that generated secrets are reused, and that the passthrough is wired into the
template.
