# Argus web

React + Vite + TypeScript dashboard for [Argus](../README.md). Talks to the FastAPI
server (`argus-http`) on `:8080`.

## Develop

```bash
npm install
npm run dev          # http://localhost:5173 — proxies /api and /health to :8080
```

Run the server alongside it:

```bash
cd ../server && argus-http
```

## Check / build

```bash
npm run lint
npm run typecheck    # tsc --noEmit
npm run build        # tsc && vite build → dist/
```

## Configuration

`VITE_ARGUS_API` overrides the API base URL (default: same origin / dev proxy). Set it
in a `.env` file for a deployed dashboard that points at a remote Argus server.

## Status

A live device table (from NetBox via the API), a drift panel (view drift + run the
confirm→apply flow), and a topology map (devices grouped by site, colored by role, with
UniFi-native uplink edges).
