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
- The NetBox API token is shared via `NETBOX_API_TOKEN` (NetBox `SUPERUSER_API_TOKEN` ==
  Argus `NETBOX_TOKEN`).
- To reset NetBox state: `docker compose down -v` (drops the Postgres/media volumes).
- **API auth (optional):** set `HTTP_TOKEN` on `argus-server` (commented in
  `docker-compose.yml`) to require `Authorization: Bearer <token>` on every `/api/*` and
  `/webhooks/*` request. `/health` and `/health/deep` stay public; leaving `HTTP_TOKEN`
  unset keeps the API open (the default). With a token set, add `-H "Authorization: Bearer
  $HTTP_TOKEN"` to the `curl` calls above, and configure the NetBox webhook to send the
  same header.
- **Scheduled drift (optional):** set `SCHEDULE_INTERVAL` (seconds, e.g. `300` = 5 min) on
  `argus-server` to run an in-process drift cycle on that interval — it runs the collector
  (`SCHEDULE_COLLECTOR`, default `unifi`), diffs against NetBox, and records the latest
  outcome at `GET /api/drift/status`. It is **read-only** (no reconcile/writes) and **off**
  by default (`0`/unset). Set `ALERT_WEBHOOK_URL` to also POST a Slack-compatible
  `{"text": ...}` alert whenever drift is detected (fired only on drift + when the URL is
  set). All three are commented in `docker-compose.yml`.
