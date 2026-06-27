# ADR-0012: Maintenance MCP Surface — a Separate `argus-maint` Server (Read/Preview-Only First)

- **Status:** Accepted — read/preview-only first cut implemented (#78, 2026-06-27)
- **Date:** 2026-06-27
- **Deciders:** Jon Freed
- **Affected:** `server/src/argus/maint_server.py` (new `FastMCP("argus-maint")`),
  `devtools/maint_tools.py` (new), `devtools/release.py` (`run_verify_captured` added),
  `pyproject.toml` (`argus-maint-mcp` entrypoint)
- **Related:** [ADR-0003](0003-discovery-reconciliation-model.md),
  [ADR-0010](0010-management-plane-contract.md),
  [ADR-0011](0011-webhook-reactions-read-side-only.md); ADR-0005 (devtools are not the product
  surface); #78

## Context

`argus.devtools.release` is a deterministic, manifest-driven release engine, exposed today only as
the `argus-release` CLI (`current` / `bump` / `verify`). The design intent recorded when it landed
(#78, "CLI now, MCP later") is to also let an **MCP control environment** invoke release/maintenance
ops directly, instead of shelling out.

The question this ADR settles is *where* those tools live and *how much* they can do. The product
`FastMCP("argus")` server is the **agent-facing network-automation surface** — read NetBox, observe
the live network, reconcile drift. Devtools are explicitly *not* part of that product surface
(`devtools/__init__.py`; `docs/ARCHITECTURE.md`). Folding `release_*` tools into the product server
would mix two unrelated audiences (an agent automating a customer's network vs. a maintainer cutting
a release of Argus itself) into one tool list, and would put a repo-mutating `bump` one call away
from the same agent that talks to a live NetBox.

## Decision

1. **A separate maintenance surface.** Maintenance tools live on a new `FastMCP("argus-maint")`
   server (`maint_server.py`) with its own `argus-maint-mcp` entrypoint — *not* on the product
   `FastMCP("argus")` server, which is left byte-for-byte unchanged. The two servers carry disjoint
   tool sets; a test asserts the product surface contains none of the maintenance tools.
2. **Read/preview-only first cut.** The first cut exposes only non-destructive ops:
   `release_current` (read the canonical version), `release_verify` (run lint/type/test/web-build
   with output captured), and `release_bump` — which is hardcoded to `dry_run=True` and returns the
   would-be diff only. No tool on this surface writes a file.
3. **No write-capable bump, yet.** A bump that actually rewrites version sites + cuts the CHANGELOG
   is **deferred**. When added it must be confirmation-gated (the two-call token pattern of
   `reconcile_apply`), mirroring ADR-0003 — a machine-driven control surface must not silently mutate
   the repo any more than it may silently mutate NetBox. The preview-only first cut is a deliberate
   safety floor, not the end state.
4. **Thin wrappers over the engine.** The tools add no logic; they resolve the repo root and call the
   existing pure-Python engine functions, returning plain JSON-able dicts (the
   `{"error": ...}` shape on a bad version / manifest mismatch mirrors the CLI). `release.py` gains
   one additive helper, `run_verify_captured`, for the capture-and-structure variant the CLI's
   stream-to-stdout `run_verify` can't provide; the existing engine is otherwise untouched.

## Rationale

- **Audience separation by construction.** Two servers means the maintenance tools can never appear
  in, or be confused with, the product network-automation tool list — the boundary is structural,
  not a naming convention.
- **Reuse, don't fork.** The tools wrap the same deterministic engine the CLI uses, so behavior can't
  drift between `argus-release` and `argus-maint-mcp`, and the manifest-consistency guarantee
  (exact occurrence counts, abort-before-write) is inherited unchanged.
- **Preview-only is safe to ship now.** `current`/`verify` are inherently read-only and `bump` has a
  clean dry-run mode that returns a structured diff without writing — so the valuable, non-destructive
  slice ships immediately while the write path waits for its own confirmation-gate decision.

## Consequences

- An MCP control environment can read the version, run the verification suite, and preview a bump
  without shelling out to the CLI — and without any path to a repo write.
- The product `argus` server and its `.mcp.json` registration are unchanged; the new server is **not**
  auto-registered in `.mcp.json` (a maintainer opts in explicitly), so existing deployments are
  unaffected.
- A future write-capable, confirmation-gated `release_bump` (and any deploy/discovery maintenance
  flows #78 floats) remains possible, but each is a deliberate follow-up — this ADR closes the door
  on a maintenance tool silently mutating the repo in its first cut.

## Alternatives Considered

- **Add `release_*` to the product `argus` server.** Rejected — mixes two unrelated audiences in one
  tool list and puts a repo-mutating op next to the live-NetBox tools; the product surface must stay
  the network-automation surface (ADR-0005's devtools-are-not-the-product boundary).
- **Ship a write-capable bump now.** Rejected for the first cut — a machine-driven surface must not
  silently mutate the repo; the write path needs the same confirmation gate reconcile has (ADR-0003),
  decided deliberately rather than bundled in here.
- **Reuse `run_verify` as-is for `release_verify`.** Rejected — it streams to stdout and returns only
  an aggregate rc, so an MCP caller gets no structured per-step result. Added a capture variant
  (`run_verify_captured`) instead of reshaping the CLI path.

## References

- [ADR-0003](0003-discovery-reconciliation-model.md) — dry-run + confirmation-gated writes (the
  posture the deferred write-bump must adopt)
- [ADR-0011](0011-webhook-reactions-read-side-only.md) — read-side-only first cut, write deferred to
  its own decision (the same safety pattern, applied to a different surface)
- `server/src/argus/devtools/release.py` — the deterministic engine these tools wrap
- #78 (this work)
