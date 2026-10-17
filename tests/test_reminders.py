from datetime import datetime, timedelta

from gameline.clock import FixedClock
from gameline.detectors import DetectedGame
from gameline.models import Deadline, Estimate, WorkingStyle
from gameline.reminders import Reminders, session_limit
from gameline.store import State, Store
from gameline.watcher import Session

NOW = datetime(2026, 10, 17, 20, 0)


def setup(tmp_path, deadlines, max_minutes=120):
    store = Store(tmp_path / "s.json")
    store.save(State(deadlines=deadlines, working_style=WorkingStyle(daily_work_hours=4, max_gaming_minutes=max_minutes)))
    sent = []
    clock = FixedClock(NOW)
    return Reminders(store, clock, notify=lambda t, b: sent.append((t, b))), clock, sent


def dl(title, days, hours):
    d = Deadline(title=title, due=NOW + timedelta(days=days))
    d.estimate = Estimate(effort_hours=hours, importance=3)
    return d


def test_launch_silent_when_on_track(tmp_path):
    r, clock, sent = setup(tmp_path, [dl("Essay", 7, 4)])
    r.on_game_started(Session(DetectedGame("Factorio", "x"), NOW))
    assert sent == []


def test_launch_names_at_risk_deadline(tmp_path):
    r, clock, sent = setup(tmp_path, [dl("CSCA48 A2", 1, 8), dl("Essay", 7, 4)])
    r.on_game_started(Session(DetectedGame("Factorio", "x"), NOW))
    (title, body), = sent
    assert "1 deadline at risk" in title and "CSCA48 A2" in body and "Essay" not in body


def test_long_session_alert_then_cooldown(tmp_path):
    r, clock, sent = setup(tmp_path, [], max_minutes=60)
    s = Session(DetectedGame("Factorio", "x"), NOW)
    clock.advance(minutes=59)
    r.on_tick([s], clock.now())
    assert sent == []
    clock.advance(minutes=2)
    r.on_tick([s], clock.now())
    clock.advance(minutes=10)
    r.on_tick([s], clock.now())  # inside cooldown
    assert len(sent) == 1
    clock.advance(minutes=55)
    r.on_tick([s], clock.now())
    assert len(sent) == 2


def test_prep_work_shortens_limit():
    style = WorkingStyle(max_gaming_minutes=120)
    assert session_limit(style, 0) == timedelta(minutes=120)
    assert session_limit(style, 4) == timedelta(minutes=90)
    assert session_limit(style, 100) == timedelta(minutes=60)
