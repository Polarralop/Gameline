"""Decide when to remind and what to say. Hooks into the watcher as a Listener.

Launch reminder: only when at least one deadline is at risk; silent otherwise.
Long-session alert: fires at the user's limit, earlier when prep work is due
soon, then repeats every repeat_minutes (a Preferences setting) so it never nags continuously.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from .clock import Clock
from .models import NotifyLevel, WorkingStyle
from .notify import notify as desktop_notify
from .planner import DeadlineStatus, at_risk_deadlines, prep_hours_needed
from .store import Store
from .watcher import Listener, Session

log = logging.getLogger(__name__)

MIN_LIMIT_MINUTES = 30
# Prep hours due in the next 48h at which the session limit is halved.
HEAVY_PREP_HOURS = 8.0


def _fmt_hours(h: float) -> str:
    if h < 1:
        return f"{max(0, round(h * 60))}m"
    return f"{h:.1f}h"


def describe(status: DeadlineStatus) -> str:
    d = status.deadline
    due = d.due.strftime("%a %-I:%M%p").replace(":00", "")
    line = f"{d.title} (due {due}): {_fmt_hours(status.remaining_hours)} left to do"
    if status.slack_hours < 0:
        line += f", {_fmt_hours(-status.slack_hours)} short"
    if status.planned_chunk:
        line += f". Planned now: {status.planned_chunk.title}"
    return line


def launch_message(game: str, risky: list[DeadlineStatus]) -> tuple[str, str]:
    n = len(risky)
    title = f"{game}: {n} deadline{'s' if n > 1 else ''} at risk"
    body = "\n".join(describe(s) for s in risky[:2])
    if n > 2:
        body += f"\n+{n - 2} more"
    return title, body


def session_limit(style: WorkingStyle, prep_hours: float) -> timedelta:
    """User limit, shrunk linearly (down to half) as near-term prep work piles up."""
    shrink = min(1.0, prep_hours / HEAVY_PREP_HOURS) * 0.5
    minutes = max(MIN_LIMIT_MINUTES, style.max_gaming_minutes * (1 - shrink))
    return timedelta(minutes=minutes)


class Reminders(Listener):
    def __init__(
        self,
        store: Store,
        clock: Clock,
        notify: Callable[[str, str], object] = desktop_notify,
        interrupt: Callable[[str, str], object] | None = None,
    ) -> None:
        self.store = store
        self.clock = clock
        self.notify = notify
        # Called (from the watcher thread) for long-session alerts at the
        # Interrupting level; the UI uses it to bring its window forward.
        self.interrupt = interrupt
        # session key -> app time of the last long-session alert
        self._last_alert: dict[str, datetime] = {}

    def on_game_started(self, session: Session) -> None:
        state = self.store.load()
        if state.working_style.notify_level == NotifyLevel.OFF:
            return
        risky = at_risk_deadlines(state.deadlines, state.working_style, self.clock.now())
        if not risky:
            log.info("On track; staying quiet for %s", session.game.name)
            return
        self.notify(*launch_message(session.game.name, risky))

    def on_game_stopped(self, session: Session, now: datetime) -> None:
        self._last_alert.pop(session.game.key, None)

    def on_tick(self, sessions: list[Session], now: datetime) -> None:
        if not sessions:
            return
        state = self.store.load()
        level = state.working_style.notify_level
        if level == NotifyLevel.OFF:
            return
        prep = prep_hours_needed(state.deadlines, state.working_style, now)
        limit = session_limit(state.working_style, prep)
        for s in sessions:
            played = s.length(now)
            if played < limit:
                continue
            last = self._last_alert.get(s.game.key)
            if last and now - last < timedelta(minutes=state.working_style.repeat_minutes):
                continue
            self._last_alert[s.game.key] = now
            hours = played.total_seconds() / 3600
            body = f"You've played {_fmt_hours(hours)}."
            if prep > 0:
                body += f" {_fmt_hours(prep)} of work is due in the next 2 days."
            title = f"Time for a break from {s.game.name}?"
            self.notify(title, body)
            if level == NotifyLevel.INTERRUPT and self.interrupt:
                self.interrupt(title, body)
