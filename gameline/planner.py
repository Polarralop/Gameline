"""Slack math: plain code that decides whether a reminder is warranted.

slack = realistic work hours available before the due date
        - remaining estimated work (scaled by working style)

Available hours are capped by the user's daily_work_hours, since nobody works
around the clock. Long-session workers need contiguous blocks, which are
harder to find, so their remaining work is padded more.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import Chunk, Deadline, Style, WorkingStyle

STYLE_FACTOR = {Style.SHORT_BURSTS: 1.0, Style.MIXED: 1.1, Style.LONG_SESSIONS: 1.25}

# A deadline is "at risk" when slack falls below this many hours...
MIN_SLACK_HOURS = 2.0
# ...or below this fraction of the remaining work.
MIN_SLACK_RATIO = 0.25


@dataclass
class DeadlineStatus:
    deadline: Deadline
    hours_until_due: float
    available_hours: float
    remaining_hours: float
    slack_hours: float
    at_risk: bool
    # A planned chunk happening now or starting soon, if any.
    planned_chunk: Chunk | None = None


def available_work_hours(now: datetime, due: datetime, daily_hours: float) -> float:
    hours_left = max(0.0, (due - now).total_seconds() / 3600)
    return min(hours_left, hours_left / 24 * daily_hours)


def current_or_next_chunk(deadline: Deadline, now: datetime, within: timedelta) -> Chunk | None:
    if not deadline.estimate:
        return None
    for c in deadline.estimate.chunks:
        if c.done or c.start is None:
            continue
        end = c.start + timedelta(hours=c.hours)
        if c.start <= now < end or now <= c.start <= now + within:
            return c
    return None


def assess(
    deadline: Deadline,
    style: WorkingStyle,
    now: datetime,
    chunk_window: timedelta = timedelta(hours=3),
) -> DeadlineStatus:
    remaining = deadline.estimate.remaining_hours if deadline.estimate else 0.0
    needed = remaining * STYLE_FACTOR[style.style]
    available = available_work_hours(now, deadline.due, style.daily_work_hours)
    slack = available - needed
    at_risk = remaining > 0 and (slack < MIN_SLACK_HOURS or slack < MIN_SLACK_RATIO * remaining)
    return DeadlineStatus(
        deadline=deadline,
        hours_until_due=(deadline.due - now).total_seconds() / 3600,
        available_hours=available,
        remaining_hours=remaining,
        slack_hours=slack,
        at_risk=at_risk,
        planned_chunk=current_or_next_chunk(deadline, now, chunk_window),
    )


def at_risk_deadlines(deadlines: list[Deadline], style: WorkingStyle, now: datetime) -> list[DeadlineStatus]:
    """Upcoming deadlines that are at risk, tightest slack first."""
    statuses = [assess(d, style, now) for d in deadlines if d.due > now]
    risky = [s for s in statuses if s.at_risk]
    return sorted(risky, key=lambda s: (s.slack_hours, -(s.deadline.estimate.importance if s.deadline.estimate else 0)))


def prep_hours_needed(deadlines: list[Deadline], style: WorkingStyle, now: datetime, horizon_hours: float = 48) -> float:
    """Remaining work due within the horizon; used to tighten long-session alerts."""
    return sum(
        assess(d, style, now).remaining_hours
        for d in deadlines
        if now < d.due <= now + timedelta(hours=horizon_hours)
    )
