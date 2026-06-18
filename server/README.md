# Argus server

Python MCP + FastAPI server. NetBox source-of-truth tools for coding agents and the
Argus web dashboard. See the [top-level README](../README.md) and
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Configure

Copy `.env.example` to `.env` (or export the vars):

```bash
NETBOX_URL=https://netbox.lan
NETBOX_TOKEN=<netbox api token>
NETBOX_VERIFY_SSL=true
HTTP_HOST=0.0.0.0
HTTP_PORT=8080

# Optional — all default to off; see .env.example for the full list.
HTTP_TOKEN=                  # bearer token for /api + /webhooks (unset = open)
SCHEDULE_INTERVAL=0          # scheduled drift loop: seconds between cycles (0 = off)
SCHEDULE_COLLECTOR=unifi     # collector the scheduled drift cycle runs
ALERT_WEBHOOK_URL=           # Slack-compatible webhook; alerts on detected drift
```

If unset, tools return a clear "NetBox not configured" message instead of erroring.

## Run

```bash
argus-mcp     # MCP server over stdio (for Claude Code etc.)
argus-http    # FastAPI HTTP server on :8080 (for the web app + webhooks)
```

The HTTP server also:

- **receives NetBox webhooks** at `POST /webhooks/netbox` — it classifies and structured-logs
  each change event (observability only; no discovery or reconcile is triggered yet).
- **runs an optional scheduled drift loop** — set `SCHEDULE_INTERVAL` (seconds) and Argus
  discovers + diffs on that interval, read-only (never `apply`). The latest outcome is served at
  `GET /api/drift/status`, and setting `ALERT_WEBHOOK_URL` POSTs a Slack-compatible alert when
  drift is found.
- **gates `/api` + `/webhooks` behind a bearer token** when `HTTP_TOKEN` is set (`/health` stays
  public); unset leaves the API open for local/dev use.

### Examples

Enable API auth, then call `/api/*` with the bearer token:

```bash
export HTTP_TOKEN="$(openssl rand -hex 32)"
argus-http
curl -H "Authorization: Bearer $HTTP_TOKEN" http://localhost:8080/api/devices
```

Enable scheduled drift detection (every 5 min) with an optional Slack alert, then read the
latest outcome:

```bash
export SCHEDULE_INTERVAL=300                                    # 0 = off
export SCHEDULE_COLLECTOR=unifi
export ALERT_WEBHOOK_URL="https://hooks.slack.com/services/…"   # optional
argus-http
curl http://localhost:8080/api/drift/status
```

Install from PyPI (the published distribution is `argus-netbox`; the import package stays `argus`
and the console scripts are `argus-mcp` / `argus-http`):

```bash
pip install argus-netbox
argus-http     # or argus-mcp
```

Container images are published to GHCR — see the top-level README's
[Published artifacts](../README.md#published-artifacts).

## Develop

```bash
ruff check src tests
mypy src
pytest -v          # offline — NetBox is mocked
```

## Tools

| Tool | Kind | Status |
| --- | --- | --- |
| `list_devices`, `get_device`, `list_prefixes`, `list_ip_addresses`, `search` | read | real (needs NetBox) |
| `list_collectors`, `discovery_scan`, `network_topology` | discovery | UniFi real — devices + clients + uplink topology (needs `UNIFI_*`); SNMP/LLDP real for non-UniFi gear (needs `SNMP_TARGETS` + `argus-netbox[discovery]`) |
| `drift_report`, `reconcile_apply` | reconcile | real — diffs and (on confirm) persists, auto-creating supporting NetBox objects |
| `health` | meta | real |
