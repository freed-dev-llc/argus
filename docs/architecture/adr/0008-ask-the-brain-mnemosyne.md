# 8. Ask the Brain — Mnemosyne integration

Date: 2026-06-24

## Status

Accepted

## Context

Argus answers *"what is on the network"* — it keeps NetBox reflecting reality. It does not
answer *"how does this technology work, and what should I do about it?"* That second question
needs an **expert**, and the family already has one:
[Mnemosyne](https://github.com/freed-dev-llc/mnemosyne), a local RAG knowledge brain whose
first pack (`ubiquiti`) covers the same vendor Argus discovers. Argus *discovers*; Mnemosyne
*explains*. Surfacing that in the dashboard makes the React app a place to both see drift and
ask what to do about it.

Mnemosyne exposes two transports: an MCP stdio server (for agents) and an HTTP server
(`mnemosyne-http`: `/ask`, `/search`, …). A browser can't speak MCP, so the dashboard path is
HTTP.

## Decision

Add an opt-in **"Ask the Brain"** dashboard panel backed by a thin server-to-server proxy:

- A new `MNEMOSYNE_URL` setting (empty disables the feature).
- `POST /api/ask` on the Argus FastAPI server proxies the question to
  `${MNEMOSYNE_URL}/ask` via `httpx` and returns Mnemosyne's `{answer, sources}` (or
  `{"error": ...}`), following Argus's existing dict-result convention. It sits under the
  `/api` prefix, so it inherits the bearer-token auth gate.
- A React `AskBrainPanel` (input → `/api/ask` → answer + cited sources).

**Argus proxies rather than calling Mnemosyne in-process.** This keeps Argus free of heavy RAG
dependencies (langchain/faiss/ollama), keeps the two services independently deployable, and
avoids browser-CORS (the call is server-to-server).

## Consequences

- The dashboard gains grounded, cited "what do I do" answers next to "what's on the network".
- Argus depends only on `httpx` (already present); no RAG deps added.
- The feature requires a reachable `mnemosyne-http` with a built pack; when `MNEMOSYNE_URL` is
  unset the endpoint returns a clear "not configured" error and the panel degrades gracefully.
- Errors (unconfigured, unreachable, non-200) are returned as `{"error": ...}`, surfaced in the
  panel — no Argus crash on a brain outage.
