# ADR-0002: Monorepo — Python MCP/FastAPI Server + React/Vite/TS Web

- **Status:** Accepted
- **Date:** 2026-06-17
- **Deciders:** Jon Freed
- **Affected:** repo layout (`server/`, `web/`), CI, Dependabot
- **Related:** [ADR-0001](0001-netbox-as-source-of-truth.md), [docs/ARCHITECTURE.md](../../ARCHITECTURE.md)

## Context

Argus needs (a) an MCP server exposing network tools to coding agents, (b) NetBox and
network-device integration, and (c) a web UI to manage and visualize the whole thing.
We must choose languages and a repository structure.

## Decision

- **Server in Python**, packaged under `server/` with a `src/argus/` layout. Use the
  official `mcp` SDK (`FastMCP`) for the stdio transport and **FastAPI** for HTTP.
- **Web in React + Vite + TypeScript**, under `web/`.
- **One monorepo** holding both apps plus shared governance (`docs/`, `.github/`).

## Rationale

- **Python for the server** is forced by the ecosystem: `pynetbox`, and the network
  discovery libraries (`napalm`, `netmiko`, `scrapli`, `pysnmp`) are all Python. The MCP
  Python SDK is first-class. This mirrors the existing `aria-unifi-mcp` server, so
  patterns (FastMCP, `tools/`, confirmation-gated writes, ruff/mypy/pytest) carry over.
- **Two transports, one tool set** keeps agent and web behavior from diverging.
- **Monorepo** keeps a cohesive product, one CHANGELOG, one set of ADRs, and atomic
  cross-cutting changes — at the cost of slightly more CI wiring (one job per app).

## Consequences

- CI has two jobs (`server`, `web`); Dependabot has three ecosystems (`pip` in
  `/server`, `npm` in `/web`, `github-actions` in `/`).
- Each app keeps its own dependency manifest and is independently buildable.
- If the web app ever needs independent release cadence, it can be split out later;
  starting unified is cheaper to maintain now.

## Alternatives Considered

- **TypeScript MCP server.** Rejected — would fight the Python-only NetBox/network
  tooling and duplicate the `aria-unifi-mcp` patterns.
- **Separate repos for server and web.** Rejected for now — more overhead (two CHANGELOGs,
  cross-repo PRs) than a solo/small project warrants.

## References

- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- Sibling server for patterns: `aria-unifi-mcp`
