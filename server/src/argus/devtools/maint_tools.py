"""Maintenance MCP tools — thin async wrappers over the deterministic release engine.

These expose the read/preview-only slice of :mod:`argus.devtools.release` (current version,
build verify, and a *dry-run-only* version-bump preview) so an MCP control environment can
invoke repo-maintenance ops directly. They live on the separate ``argus-maint`` surface — not
the product ``argus`` network-automation tool set — see ADR-0012.

Safety posture: nothing here writes. ``release_bump`` is hardcoded to ``dry_run=True`` and
returns the would-be diff only; a write-capable bump (and its confirmation gate) is a
deliberately deferred follow-up. Use the ``argus-release`` CLI to perform an actual bump.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .release import (
    ConsistencyError,
    _today,
    bump,
    current_version,
    find_repo_root,
    load_config,
    run_verify_captured,
)


async def release_current() -> dict[str, Any]:
    """Report the repository's canonical current version (read-only)."""
    root = find_repo_root()
    cfg = load_config(root)
    return {"version": current_version(root, cfg)}


async def release_verify() -> dict[str, Any]:
    """Run the release verification suite (lint / type / test / web build), read-only.

    Each step is executed with its output captured (nothing is written), off the event loop.
    Returns a per-step record plus an aggregate ``ok``.
    """
    root = find_repo_root()
    steps = await asyncio.to_thread(run_verify_captured, root)
    return {"ok": all(step["ok"] for step in steps), "steps": steps}


async def release_bump(version: str, date: str | None = None) -> dict[str, Any]:
    """Preview a version bump — always dry-run, never writes.

    Computes and validates every version site plus the CHANGELOG cut against the live files
    and returns the would-be changes. This is preview-only: no file is modified (writes are a
    deferred follow-up — see ADR-0012). On a bad version or a manifest mismatch it returns an
    ``{"error": ...}`` shape instead of raising.

    Args:
        version: The proposed new version, e.g. "0.1.8".
        date: CHANGELOG date for the cut (default: today / ``$ARGUS_RELEASE_DATE``).
    """
    root = find_repo_root()
    when = date or _today()
    try:
        result = await asyncio.to_thread(bump, root, version, when=when, dry_run=True)
    except (ConsistencyError, ValueError) as exc:
        return {"error": str(exc)}
    return result.to_dict()
