# Role: `argus_deploy`

Deploys the self-contained Argus stack (NetBox + its datastore + Argus server + web) to a
Docker host, replacing the manual rsync / secret-generation / `docker compose up` steps.

What it does:

1. (Optional) `git` the Argus repo to `argus_dest` (`argus_manage_repo: true`).
2. Render `deploy/.env` — **secrets are generated once and reused** from the existing `.env`
   on subsequent runs, so re-running never rotates the NetBox DB password or API token. The
   template covers every stack var, so optional values (`HTTP_TOKEN`, the `SCHEDULE_*`
   pair, `ALERT_WEBHOOK_URL`) are preserved across runs rather than dropped.
3. `docker compose up` (build + start) via `community.docker.docker_compose_v2`; a `.env`
   change triggers a recreate handler.

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
| `argus_schedule_interval` / `argus_schedule_collector` | `""` | In-process drift schedule (seconds / collector). Blank reuses existing `.env` (compose defaults `0` / `unifi`). |
| `argus_alert_webhook_url` | `""` | Slack-compatible webhook; POSTs on drift when set. Blank reuses existing `.env`. |
| `argus_docker_path` | macOS OrbStack/Homebrew + system paths | PATH so the module finds `docker`. |

## Usage

```bash
cd ansible
ansible-galaxy collection install -r requirements.yml
cp inventory/hosts.example.yml inventory/hosts.yml   # edit
ansible-playbook -i inventory/hosts.yml deploy-argus.yml
```

Idempotent: a second run with no config change makes no changes (secrets are reused).
