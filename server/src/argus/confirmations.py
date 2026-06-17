"""Confirmation store gating state-changing actions (e.g. reconcile apply).

A tool returns a confirmation token instead of acting; a second, explicit call with that
token performs the action. Tokens expire after a short TTL. This keeps an agent from
silently mutating the source of truth.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass
class PendingAction:
    """An action awaiting explicit confirmation."""

    action_id: str
    tool_name: str
    description: str
    created_at: datetime
    expires_at: datetime
    tool_args: dict[str, Any] = field(default_factory=dict)


class ConfirmationStore:
    """In-memory store of pending, confirmable actions."""

    def __init__(self, ttl_minutes: int = 5) -> None:
        self._actions: dict[str, PendingAction] = {}
        self.ttl = timedelta(minutes=ttl_minutes)

    def create(
        self, tool_name: str, description: str, tool_args: dict[str, Any] | None = None
    ) -> PendingAction:
        """Register a pending action and return it (with its ``action_id``)."""
        self.cleanup_expired()
        now = datetime.now(UTC)
        action = PendingAction(
            action_id=secrets.token_urlsafe(16),
            tool_name=tool_name,
            description=description,
            created_at=now,
            expires_at=now + self.ttl,
            tool_args=tool_args or {},
        )
        self._actions[action.action_id] = action
        return action

    def get(self, action_id: str) -> PendingAction | None:
        """Return a pending action, or ``None`` if missing or expired."""
        action = self._actions.get(action_id)
        if action and datetime.now(UTC) > action.expires_at:
            del self._actions[action_id]
            return None
        return action

    def confirm(self, action_id: str) -> tuple[PendingAction | None, str | None]:
        """Consume and return an action. Returns ``(action, error)``."""
        action = self.get(action_id)
        if not action:
            return None, "Action expired or not found."
        del self._actions[action_id]
        return action, None

    def cleanup_expired(self) -> int:
        """Drop expired actions; return how many were removed."""
        now = datetime.now(UTC)
        expired = [aid for aid, a in self._actions.items() if a.expires_at < now]
        for aid in expired:
            del self._actions[aid]
        return len(expired)

    def list_pending(self) -> list[PendingAction]:
        """Return all currently pending (non-expired) actions."""
        self.cleanup_expired()
        return list(self._actions.values())
