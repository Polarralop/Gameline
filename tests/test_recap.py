from datetime import datetime, timedelta

from gameline.detectors import DetectedGame
from gameline.models import Chunk, Deadline, Estimate
from gameline.recap import SessionRecorder, build, month_bounds, week_bounds
from gameline.store import PlayedSession, State, Store
from gameline.watcher import Session

NOW = datetime(2026, 10, 17, 12, 0)  # a Saturday


def test_bounds():
    assert week_bounds(NOW) == (datetime(2026, 10, 12), datetime(2026, 10, 19))
    assert week_bounds(NOW, -1)[0] == datetime(2026, 10, 5)
    assert month_bounds(NOW) == (datetime(2026, 10, 1), datetime(2026, 11, 1))
    assert month_bounds(NOW, 3) == (datetime(2027, 1, 1), datetime(2027, 2, 1))


def test_week_recap_totals_and_level():
    d = Deadline("CSCA48 A2", NOW + timedelta(days=3))
    d.estimate = Estimate(9, 4, [
        Chunk("Q1", 3, done=True, done_at=datetime(2026, 10, 13, 20)),
        Chunk("Q2", 4, done=True, done_at=datetime(2026, 10, 15, 21)),
        Chunk("old", 5, done=True, done_at=datetime(2026, 10, 2, 9)),  # last week: not counted
        Chunk("Q3", 2),
    ])
    done = Deadline("WSTC02 essay", NOW - timedelta(days=1), completed_at=datetime(2026, 10, 16, 10))
    state = State(deadlines=[d, done], sessions=[
        PlayedSession("Factorio", datetime(2026, 10, 13, 22), datetime(2026, 10, 14, 1)),
        PlayedSession("Factorio", datetime(2026, 10, 16, 20), datetime(2026, 10, 16, 21)),
        PlayedSession("Hades", datetime(2026, 10, 15, 23), datetime(2026, 10, 15, 23, 30)),
    ])
    r = build(state, "week", NOW)
    assert r.work_hours == 7 and r.tasks_done == 2 and r.level == "medium"
    assert [(g.name, g.minutes, g.sessions) for g in r.games] == [("Factorio", 240, 2), ("Hades", 30, 1)]
    assert r.deadlines_done == ["WSTC02 essay"]
    assert [b.label for b in r.buckets][:2] == ["Mon", "Tue"] and r.buckets[1].work_hours == 3  # Oct 13 is a Tuesday


def test_recorder_saves_sessions_and_skips_blips(tmp_path):
    store = Store(tmp_path / "s.json")
    rec = SessionRecorder(store)
    rec.on_game_stopped(Session(DetectedGame("Factorio", "x"), NOW), NOW + timedelta(minutes=90))
    rec.on_game_stopped(Session(DetectedGame("Launcher", "x"), NOW), NOW + timedelta(seconds=20))
    assert [(s.game, s.minutes) for s in store.load().sessions] == [("Factorio", 90)]
