"""Event-triggered, read-only drift reactions to authenticated NetBox webhooks.

When opt-in reactions are enabled (``WEBHOOK_REACTIONS_ENABLED``), an *authenticated* NetBox
webhook for an allow-listed model triggers exactly one extra run of the existing read-only
drift cycle (:func:`argus.scheduler.run_drift_cycle`) — discovery + diff + optional alert, and
**never** an apply/write. The no-write guarantee is inherited by construction: this module only
ever calls ``run_drift_cycle`` and imports nothing from the reconcile/write path.

Two concerns are kept separate:

- :func:`should_react` is a **pure** predicate (enabled, authenticated, allow-listed) with no
  side effects, so it is trivial to unit-test.
- :func:`trigger_reaction` schedules the cycle fire-and-forget and applies **single-flight +
  trailing-coalesce** (no timers): if a cycle is already running, the event sets a ``pending``
  flag instead of starting a second concurrent cycle; when the running cycle finishes, at most
  one trailing cycle runs to absorb the coalesced burst. A burst of N events therefore collapses
  to "one cycle now + at most one trailing cycle." Every cycle exception is caught and logged so
  a failed reaction never crashes anything or leaks the retained task reference.
"""

from __future__ import annotations

import asyncio
import logging

from . import scheduler
from .config import Settings
from .webhooks import NetBoxEvent

logger = logging.getLogger(__name__)

# Single-flight + trailing-coalesce state (no timers). ``_running`` guards against concurrent
# cycles; ``_pending`` records that event(s) arrived while a cycle was in flight; ``_task`` is a
# retained reference to the in-flight fire-and-forget task so it cannot be garbage-collected
# mid-run (a task with no held reference can be GC'd, cancelling it silently).
_running = False
_pending = False
_task: asyncio.Task[None] | None = None


def _parse_models(raw: str) -> set[str]:
    """Parse the comma-separated reaction model allow-list into a set (blanks dropped)."""
    return {model.strip() for model in raw.split(",") if model.strip()}


def should_react(event: NetBoxEvent, settings: Settings) -> bool:
    """Return ``True`` when this event should trigger a read-only drift reaction.

    Pure and side-effect-free. All three conditions must hold:

    - reactions are enabled (``WEBHOOK_REACTIONS_ENABLED``);
    - the request was authenticated — at least one auth mechanism is configured, either bearer
      auth (``http_auth_enabled``; the request already passed the middleware) or webhook HMAC
      verification (``webhook_verification_enabled``; verified in-handler). An open endpoint with
      neither secret set is forgeable, so it never reacts; and
    - the event's ``model`` is in the configured allow-list (``WEBHOOK_REACTION_MODELS``).

    Args:
        event: The classified inbound webhook event.
        settings: The active runtime settings.

    Returns:
        ``True`` only when enabled, authenticated, and the model is allow-listed.
    """
    if not settings.reactions_enabled:
        return False
    if not (settings.http_auth_enabled or settings.webhook_verification_enabled):
        return False
    return event.model in _parse_models(settings.webhook_reaction_models)


def trigger_reaction(collector: str) -> asyncio.Task[None] | None:
    """Schedule a read-only drift cycle, applying single-flight + trailing-coalesce.

    Non-blocking: never awaits the cycle, so the webhook ack returns immediately. If a cycle is
    already running, this records a pending event and returns the in-flight task (the running
    chain will run one trailing cycle when it finishes). Otherwise it starts the cycle as a
    fire-and-forget task whose reference is retained module-side so it is not GC'd mid-run.

    Args:
        collector: The collector the drift cycle should observe.

    Returns:
        The in-flight :class:`asyncio.Task` (newly started or already running).
    """
    global _running, _pending, _task
    if _running:
        _pending = True
        return _task
    _running = True
    _task = asyncio.create_task(_run_chain(collector))
    return _task


async def _run_chain(collector: str) -> None:
    """Run the leading drift cycle plus, if events coalesced, exactly one trailing cycle.

    Single-flight is enforced by the ``_running`` flag set in :func:`trigger_reaction`. Any
    events that arrive while the leading cycle runs set ``_pending``; when it finishes, a single
    trailing cycle absorbs them, then the chain stops and resets state so the next event starts a
    fresh chain. Each cycle's exceptions are swallowed and logged so a failed reaction never
    crashes the loop or leaks the task.
    """
    global _running, _pending, _task
    try:
        await _safe_cycle(collector)
        if _pending:
            _pending = False
            await _safe_cycle(collector)
    finally:
        _running = False
        _pending = False
        _task = None


async def _safe_cycle(collector: str) -> None:
    """Run one read-only drift cycle, swallowing and logging any exception."""
    try:
        await scheduler.run_drift_cycle(collector)
    except Exception:
        logger.exception("webhook reaction drift cycle raised; continuing")


def reset_state() -> None:
    """Reset the single-flight/coalesce module state. Test seam only."""
    global _running, _pending, _task
    _running = False
    _pending = False
    _task = None
