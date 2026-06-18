"""In-process scheduled discovery + drift alerting.

A dependency-free asyncio task runs a discovery collector on a fixed interval, diffs the
result against NetBox, and records the latest outcome so it can be surfaced two ways: a
status endpoint (``GET /api/drift/status``) plus structured logs, and an optional outbound
webhook (Slack-compatible ``{"text": ...}``) fired only when drift is present and an alert
URL is configured. The loop is opt-in — it never starts unless ``SCHEDULE_INTERVAL`` is a
positive number of seconds. Drift is read-only: no reconcile or NetBox write happens here.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from .config import get_settings
from .tools.reconcile_tools import drift_report

logger = logging.getLogger(__name__)

# Webhook POST timeout (seconds). Kept short so a slow alert endpoint never stalls a cycle.
_ALERT_TIMEOUT = 10.0


@dataclass
class DriftStatus:
    """Outcome of the most recent drift cycle.

    Attributes:
        last_run: ISO-8601 UTC timestamp of the last cycle, or None if it never ran.
        collector: Collector observed in the last cycle, or None.
        change_count: Number of proposed changes (drift items); None on error / never run.
        summary: The reconcile plan summary dict; None on error / never run.
        ok: True when no drift, False when drift is present, None when never run or errored.
        error: Error message from the last cycle, or None.
    """

    last_run: str | None = None
    collector: str | None = None
    change_count: int | None = None
    summary: dict[str, Any] | None = None
    ok: bool | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view of the status."""
        return asdict(self)


_status = DriftStatus()


def get_drift_status() -> DriftStatus:
    """Return the latest recorded drift status."""
    return _status


async def run_drift_cycle(collector: str | None = None) -> DriftStatus:
    """Run one discovery + drift cycle and record the outcome.

    This is the testable tick: it observes ``collector`` (or the configured default) via
    :func:`drift_report`, updates the module status, emits a structured log line, and fires
    the alert webhook when drift is present and a webhook URL is configured. It performs no
    writes — drift is strictly read-only.

    Args:
        collector: Collector to observe; defaults to ``settings.schedule_collector``.

    Returns:
        The updated :class:`DriftStatus`.
    """
    global _status
    settings = get_settings()
    name = collector or settings.schedule_collector
    timestamp = datetime.now(UTC).isoformat()

    result = await drift_report(name)

    if "error" in result:
        _status = DriftStatus(
            last_run=timestamp, collector=name, ok=None, error=result["error"]
        )
        logger.warning(
            "drift cycle failed: collector=%s error=%s",
            name,
            result["error"],
            extra={"collector": name, "drift_error": result["error"]},
        )
        return _status

    changes = result.get("changes", [])
    summary = result.get("summary")
    count = len(changes)
    _status = DriftStatus(
        last_run=timestamp,
        collector=name,
        change_count=count,
        summary=summary,
        ok=count == 0,
    )
    logger.info(
        "drift cycle: collector=%s changes=%d ok=%s",
        name,
        count,
        count == 0,
        extra={"collector": name, "change_count": count, "drift_ok": count == 0},
    )

    if count > 0 and settings.alert_webhook_url:
        await _send_alert(settings.alert_webhook_url, name, count, summary)

    return _status


async def _send_alert(
    url: str, collector: str, count: int, summary: dict[str, Any] | None
) -> None:
    """POST a Slack-compatible drift alert; swallow and log any failure.

    A failed alert must never crash the drift cycle, so every exception is caught and
    logged instead of propagating.

    Args:
        url: Webhook URL to POST to.
        collector: Collector that produced the drift.
        count: Number of proposed changes.
        summary: The reconcile plan summary, for context.
    """
    text = f"Argus drift on '{collector}': {count} change(s) detected."
    if summary:
        text += f" Summary: {summary}"
    try:
        async with httpx.AsyncClient(timeout=_ALERT_TIMEOUT) as client:
            await client.post(url, json={"text": text})
    except Exception:
        logger.exception("drift alert webhook failed: collector=%s", collector)


async def scheduler_loop() -> None:
    """Run :func:`run_drift_cycle` forever on the configured interval.

    Sleeps first (so startup is never blocked) and never lets a single failed cycle kill
    the loop — every cycle exception is logged and the loop continues. Cancellation, raised
    on shutdown, propagates normally to stop the task.
    """
    settings = get_settings()
    interval = settings.schedule_interval
    logger.info(
        "drift scheduler started: interval=%ss collector=%s",
        interval,
        settings.schedule_collector,
    )
    while True:
        await asyncio.sleep(interval)
        try:
            await run_drift_cycle()
        except Exception:
            logger.exception("drift scheduler cycle raised; continuing")
