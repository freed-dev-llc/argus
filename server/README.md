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
```

If unset, tools return a clear "NetBox not configured" message instead of erroring.

## Run

```bash
argus-mcp     # MCP server over stdio (for Claude Code etc.)
argus-http    # FastAPI HTTP server on :8080 (for the web app + webhooks)
```

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
| `list_collectors`, `discovery_scan` | discovery | UniFi real (needs `UNIFI_*`); SNMP/LLDP + DHCP/ARP stubbed |
| `drift_report`, `reconcile_apply` | reconcile | stub, confirmation-gated |
| `health` | meta | real |
