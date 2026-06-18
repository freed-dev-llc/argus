# Handoff — Sage / Nova / Vera workflow

This directory is the shared working state for Argus's three-role build loop.
The roles are invoked via the `/sage`, `/nova`, and `/vera` slash commands; their
definitions live in `SAGE.md`, `NOVA.md`, and `VERA.md` at the repo root.

## The loop

```
Jon ──┐
      ▼
   /sage  (Architect) ── writes the brief, owns the merge gate
      │   current-brief.md
      ▼
   /nova  (Builder) ──── plans, then builds exactly the brief
      │   build-complete.md
      ▼
   /vera  (Reviewer) ─── reviews only what Nova listed
      │   review-result.md  →  Ready for Nova: YES / NO
      ▼
   back to Sage → Jon's go-ahead → squash-merge to main → session-checkpoint.md
```

## Files (created on demand during a session)

| File | Written by | Purpose |
|------|-----------|---------|
| `current-brief.md` | Sage (+ Nova Plan section) | The single source of truth for the active step |
| `build-log.md` | Nova | Running log: step status, files changed, decisions, Known Gaps |
| `build-complete.md` | Nova | Handoff to Vera: files + line ranges, tests run, `Ready for Review: YES` |
| `review-result.md` | Vera | Findings: Must Fix / Should Fix / Escalate to Sage / Cleared |
| `session-checkpoint.md` | Sage | State + resume prompt at the end of a session (read first next time) |

These are session artifacts — none of them exist yet, and they are gitignored (only this
`README.md` is tracked). Each role creates the files it owns as the loop runs. Argus's
canonical project status lives in `docs/ROADMAP.md` (phase checkmarks) and `CHANGELOG.md`
`[Unreleased]`, not here.

> Imported from the Aria project's Sage/Nova/Vera system (also used in Leeloo) and adapted to
> Argus's stack: NetBox-as-source-of-truth, the `server/` Python MCP + FastAPI app and `web/`
> React/Vite app, signed-commit + squash-only PRs, and required `server` + `web` CI checks.
