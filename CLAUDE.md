# CLAUDE.md — Argus

> Orientation for coding-agent sessions (tracked in this repo).

## What this is

**Argus** = NetBox-backed network source-of-truth automation server for MCP coding
agents, owned by `freed-dev-llc`. NetBox is authoritative; Argus discovers live network
state, diffs it, and reconciles NetBox to match. Monorepo: `server/` (Python MCP +
FastAPI) and `web/` (React + Vite + TS).

## Conventions (freed-dev-llc baseline)

- **Sign commits** (`git commit -S`, key `77200F1B9C2465AB`); do NOT set `gpg.format=ssh`.
- **No agent attribution.** Do NOT add `Co-Authored-By: Claude` (or any agent),
  `🤖 Generated with Claude Code`, or similar attribution lines/trailers to commit
  messages or PR bodies. Author commits as the user only.
- **Land via PR**, squash-only. `main` is protected (signatures, codeowner review,
  required checks `server` + `web`). `required_approving_review_count=0` → self-merge
  after green CI via `gh pr merge --squash`.
- Update `CHANGELOG.md` under `[Unreleased]`; capture architecture in `docs/architecture/adr/`.

## Common commands

```bash
# server
cd server && pip install -e ".[dev]"
ruff check src tests && mypy src && pytest -v
argus-http   # FastAPI :8080      argus-mcp   # MCP stdio

# web
cd web && npm install
npm run lint && npx tsc --noEmit && npm run build && npm run dev   # :5173
```

## Layout

- `server/src/argus/config.py` — env settings (`NETBOX_URL`, `NETBOX_TOKEN`, ...).
- `server/src/argus/netbox/client.py` — `pynetbox` wrapper (real reads).
- `server/src/argus/discovery/` — `Collector` ABC + vendor-pack collectors (`vendors/`),
  the `practices` SPI (ADR-0009), and the management-plane contract (ADR-0010).
- `server/src/argus/reconcile/engine.py` — diff/apply engine (dry-run default, confirmation-gated).
- `server/src/argus/tools/` — read / discovery / reconcile / practices tool functions (the agent surface).
- `server/src/argus/{server,http_server}.py` — MCP stdio + FastAPI transports.

## Status

v0.1.6. The full loop is **implemented and validated end-to-end** against a live UniFi
network + NetBox 4.6: read tools (need a live NetBox to return data), discovery (devices,
clients, uplink topology), and reconcile (diff → confirm → apply, with NetBox DCIM/IPAM
write-back). Discovery refactored into vendor packs (v0.1.5); a vendor-pack `practices` SPI
(ADR-0009) and a read-only management-plane contract (ADR-0010) landed in v0.1.6 — both
advisory/read-only. See `docs/ROADMAP.md` and `CHANGELOG.md`.
