from datetime import datetime, timedelta

from gameline.clock import FixedClock
from gameline.detectors import DetectedGame, GameDetector
from gameline.watcher import Listener, Watcher


class FakeDetector(GameDetector):
    name = "fake"

    def __init__(self):
        self.games = []

    def get_running_games(self):
        return list(self.games)


class Recorder(Listener):
    def __init__(self):
        self.events = []

    def on_game_started(self, session):
        self.events.append(("start", session.game.name))

    def on_game_stopped(self, session, now):
        self.events.append(("stop", session.game.name, session.length(now)))


def test_start_and_stop_events_with_session_length():
    det, rec = FakeDetector(), Recorder()
    clock = FixedClock(datetime(2026, 10, 17, 20, 0))
    w = Watcher([det], rec, clock=clock)

    w.poll_once()
    det.games = [DetectedGame("Factorio", "fake")]
    w.poll_once()
    w.poll_once()  # still running: no duplicate start
    clock.advance(hours=2)
    det.games = []
    w.poll_once()

    assert rec.events == [("start", "Factorio"), ("stop", "Factorio", timedelta(hours=2))]


def test_listener_errors_do_not_kill_the_loop():
    class Broken(Listener):
        def on_game_started(self, session):
            raise RuntimeError("boom")

    det = FakeDetector()
    det.games = [DetectedGame("X", "fake")]
    w = Watcher([det], Broken(), clock=FixedClock(datetime(2026, 1, 1)))
    w.poll_once()
    assert "x" in w.sessions
