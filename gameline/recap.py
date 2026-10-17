"""Weekly and monthly recaps: work done, how heavy it was, and which games
took the time. Plain code over the saved state: ticked tasks (by done_at)
and the finished gaming sessions the watcher records.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .store import PlayedSession, State
from .watcher import Listener, Session

# Hours of finished work per week that count as a light / medium / heavy load.
LIGHT_UNDER, HEAVY_FROM = 6.0, 15.0


@dataclass
class Bucket:
    label: str
    start: datetime
    work_hours: float = 0.0
    game_hours: float = 0.0


@dataclass
class GameTally:
    name: str
    minutes: float = 0.0
    sessions: int = 0


@dataclass
class Recap:
    kind: str  # "week" or "month"
    start: datetime
    end: datetime
    buckets: list[Bucket] = field(default_factory=list)
    work_hours: float = 0.0
    tasks_done: int = 0
    deadlines_done: list[str] = field(default_factory=list)
    games: list[GameTally] = field(default_factory=list)

    @property
    def game_hours(self) -> float:
        return sum(g.minutes for g in self.games) / 60

    @property
    def sessions(self) -> int:
        return sum(g.sessions for g in self.games)

    @property
    def level(self) -> str:
        """light / medium / heavy, scaled to the period's length in weeks."""
        weeks = (self.end - self.start).days / 7
        per_week = self.work_hours / weeks if weeks else 0
        if per_week < LIGHT_UNDER:
            return "light"
        return "heavy" if per_week >= HEAVY_FROM else "medium"


def week_bounds(day: datetime, offset: int = 0) -> tuple[datetime, datetime]:
    """Monday 00:00 to next Monday 00:00, shifted by offset weeks."""
    monday = (day - timedelta(days=day.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    start = monday + timedelta(weeks=offset)
    return start, start + timedelta(weeks=1)


def month_bounds(day: datetime, offset: int = 0) -> tuple[datetime, datetime]:
    month_index = day.year * 12 + day.month - 1 + offset
    year, month = divmod(month_index, 12)
    start = datetime(year, month + 1, 1)
    days = calendar.monthrange(start.year, start.month)[1]
    return start, start + timedelta(days=days)


def build(state: State, kind: str, now: datetime, offset: int = 0) -> Recap:
    start, end = (week_bounds if kind == "week" else month_bounds)(now, offset)
    recap = Recap(kind, start, end)

    if kind == "week":
        recap.buckets = [Bucket((start + timedelta(days=i)).strftime("%a"), start + timedelta(days=i)) for i in range(7)]
    else:  # one bar per week of the month: 1–7, 8–14, ...
        day = start
        while day < end:
            recap.buckets.append(Bucket(f"{day.strftime('%b')} {day.day}", day))
            day += timedelta(days=7)

    def bucket_for(t: datetime) -> Bucket:
        return [b for b in recap.buckets if b.start <= t][-1]

    for d in state.deadlines:
        if d.completed_at and start <= d.completed_at < end:
            recap.deadlines_done.append(d.title)
        for c in d.estimate.chunks if d.estimate else []:
            if c.done and c.done_at and start <= c.done_at < end:
                recap.work_hours += c.hours
                recap.tasks_done += 1
                bucket_for(c.done_at).work_hours += c.hours

    games: dict[str, GameTally] = {}
    for s in state.sessions:
        if not (start <= s.start < end):
            continue
        tally = games.setdefault(s.game, GameTally(s.game))
        tally.minutes += s.minutes
        tally.sessions += 1
        bucket_for(s.start).game_hours += s.minutes / 60
    recap.games = sorted(games.values(), key=lambda g: -g.minutes)
    return recap


class SessionRecorder(Listener):
    """Watcher listener that saves each finished session for recaps."""

    def __init__(self, store) -> None:
        self.store = store

    def on_game_stopped(self, session: Session, now: datetime) -> None:
        if (now - session.started_at).total_seconds() < 60:
            return  # ignore blips, e.g. a launcher that closes straight away
        with self.store.lock:
            state = self.store.load()
            state.sessions.append(PlayedSession(session.game.name, session.started_at, now))
            self.store.save(state)
