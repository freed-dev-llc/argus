# Deploying Argus (self-contained validation stack)

This brings up a complete, self-contained Argus environment for live validation:

| Service | Purpose | Published |
| --- | --- | --- |
| `netbox` + `netbox-worker` | NetBox (the source of truth) | `:8096` (UI) |
| `netbox-postgres`, `netbox-redis` | NetBox's datastore | internal only |
| `argus-server` | MCP + FastAPI server | `127.0.0.1:8094` (API) |
| `argus-web` | Dashboard (nginx) | `:8095` |

NetBox's Postgres/Redis are **not** published, so they won't collide with any host
services. NetBox is auto-provisioned with a superuser and the API token Argus uses.

## 1. Configure

```bash
cd deploy
cp .env.example .env
# generate secrets:
{
  echo "NETBOX_SECRET_KEY=$(openssl rand -base64 50 | tr -d '\n')"
  echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"
  echo "NETBOX_SUPERUSER_PASSWORD=$(openssl rand -hex 24)"
  echo "NETBOX_API_TOKEN=$(openssl rand -hex 20)"
} >> .env
# then set UNIFI_URL + UNIFI_API_TOKEN (+ UNIFI_SITE) in .env
```

> Note: `>>` appends the generated secrets *below* the empty placeholders copied from
> `.env.example`, leaving duplicate keys. Compose uses the last value for a duplicate key, so
> this works as-is — just edit the appended lines (not the empty placeholders above) if you
> need to change a secret later.

## 2. Bring it up

```bash
docker compose --env-file .env up -d --build
```

First boot runs NetBox migrations + provisioning (~1–3 min). Watch readiness:

```bash
docker compose ps
docker compose logs -f netbox        # until "healthy"
```

## 3. Validate the loop

```bash
# Argus sees NetBox?
curl -s localhost:8094/health/deep            # {"status":"ok","netbox_configured":true}

# Observe the live network (reads UniFi):
curl -s -X POST localhost:8094/api/collectors/unifi/scan | jq

# What would change in NetBox?
curl -s localhost:8094/api/drift | jq

# Apply (two-step, confirmation-gated):
TOKEN=$(curl -s -X POST localhost:8094/api/reconcile | jq -r .confirm_token)
curl -s -X POST "localhost:8094/api/reconcile?confirm_token=$TOKEN" | jq

# Confirm NetBox was populated:
curl -s localhost:8094/api/devices | jq '.count'
```

Or use the dashboard at `http://<host>:8095` (Devices / IPAM / Drift / Topology), and the
NetBox UI at `http://<host>:8096` (log in as `admin`).

## Notes

- `NETBOX_IMAGE` pins the NetBox version; bump it in `.env` as needed.
- The NetBox API token is shared via `NETBOX_API_TOKEN`: the one-shot `netbox-init` service
  creates a v1 token with that value (NetBox's own provisioning only mints v2 tokens, which
  pynetbox can't present), and `argus-server` reads the same value as `NETBOX_TOKEN`.
- To reset NetBox state: `docker compose down -v` (drops the Postgres/media volumes).
- **API auth (optional):** set `HTTP_TOKEN` in `.env` to require `Authorization: Bearer
  <token>` on every `/api/*` and `/webhooks/*` request (constant-time compare). `/health`
  and `/health/deep` stay public; leaving `HTTP_TOKEN` unset keeps the API open (the
  default). The same `.env` value reaches **both** services — `argus-server` enforces it
  and `argus-web`'s nginx forwards it on the dashboard's `/api` proxy — so the bundled
  dashboard keeps working against an auth-enabled API. For direct `curl` calls, add `-H
  "Authorization: Bearer $HTTP_TOKEN"`, and configure the NetBox webhook to send the same
  header.
- **Scheduled drift (optional):** set `SCHEDULE_INTERVAL` (seconds, e.g. `300` = 5 min) in
  `.env` to run an in-process drift cycle on that interval — it runs the collector
  (`SCHEDULE_COLLECTOR`, default `unifi`), diffs against NetBox, and records the latest
  outcome at `GET /api/drift/status`. It is **read-only** (no reconcile/writes) and **off**
  by default (`0`/unset). Set `ALERT_WEBHOOK_URL` to also POST a Slack-compatible
  `{"text": ...}` alert whenever drift is detected (fired only on drift + when the URL is
  set).
- **Expose NetBox on a public hostname (Cloudflare Tunnel):** to reach the NetBox UI at a
  subdomain like `https://netbox.example.com` — cleaner than a sub-path, since NetBox is a
  root-served Django app — point a tunnel ingress rule at NetBox's published port and set the
  CSRF origin so login works:

  ```yaml
  # ~/.cloudflared/config.yml  (or add a "Public Hostname" in the Zero Trust dashboard)
  ingress:
    - hostname: argus.example.com      # existing — Argus dashboard
      service: http://localhost:8095
    - hostname: netbox.example.com     # new — NetBox UI/API
      service: http://localhost:8096
    - service: http_status:404
  ```

  Create the DNS route (`cloudflared tunnel route dns <tunnel> netbox.example.com`) and set
  `NETBOX_CSRF_TRUSTED_ORIGINS=https://netbox.example.com` in `.env`. Cloudflare terminates TLS
  and forwards `X-Forwarded-Proto: https`, so NetBox v4 rejects the login POST as a CSRF failure
  without a matching trusted origin. (If `cloudflared` runs as a container on the compose
  network instead of on the host, use `service: http://netbox:8080`.) **Security:** this puts
  NetBox's read/write UI on the public internet — gate the hostname behind Cloudflare Access (or
  equivalent); don't rely on the NetBox login alone.
- **Pre-built images:** released `v*` tags publish the server and web images to GHCR —
  `ghcr.io/freed-dev-llc/argus-server` and `ghcr.io/freed-dev-llc/argus-web` (tags `0.1.6` /
  `latest`). The default compose file builds locally (`--build`); to run the published images
  instead, point the `argus-server` / `argus-web` services at those tags. The server package
  is also on PyPI (`pip install argus-netbox` — the import name is still `argus`).
