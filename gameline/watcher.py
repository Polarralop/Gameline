"""Polling loop: turns detector snapshots into game start/stop events.

Runs on a worker thread (rumps owns the main thread). Each poll diffs the
current set of running games against the last one. Session start times come
from the app clock, not the process start time, so demo-mode acceleration
applies to session length too.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .clock import Clock
from .detectors import DetectedGame, GameDetector, get_running_games

log = logging.getLogger(__name__)


@dataclass
class Session:
    game: DetectedGame
    started_at: datetime

    def length(self, now: datetime) -> timedelta:
        return now - self.started_at


class Listener:
    """Override any of these; the watcher calls them from its thread."""

    def on_game_started(self, session: Session) -> None: ...

    def on_game_stopped(self, session: Session, now: datetime) -> None: ...

    def on_tick(self, sessions: list[Session], now: datetime) -> None: ...


class Listeners(Listener):
    """Fan one watcher's events out to several listeners."""

    def __init__(self, *listeners: Listener) -> None:
        self.listeners = listeners

    def _each(self, method: str, *args) -> None:
        # One listener failing (say, a notification error) mustn't stop the others.
        for listener in self.listeners:
            try:
                getattr(listener, method)(*args)
            except Exception:
                log.exception("Listener error in %s.%s", type(listener).__name__, method)

    def on_game_started(self, session: Session) -> None:
        self._each("on_game_started", session)

    def on_game_stopped(self, session: Session, now: datetime) -> None:
        self._each("on_game_stopped", session, now)

    def on_tick(self, sessions: list[Session], now: datetime) -> None:
        self._each("on_tick", sessions, now)


class Watcher:
    def __init__(
        self,
        detectors: Iterable[GameDetector] | Callable[[], Iterable[GameDetector]],
        listener: Listener,
        clock: Clock | None = None,
        interval: float = 5.0,
    ) -> None:
        # Accept a callable so newly tagged games are picked up without a restart.
        self._detectors = detectors if callable(detectors) else (lambda d=list(detectors): d)
        self.listener = listener
        self.clock = clock or Clock()
        self.interval = interval
        self.sessions: dict[str, Session] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def poll_once(self) -> None:
        now = self.clock.now()
        running = {g.key: g for g in get_running_games(self._detectors())}

        for key, game in running.items():
            if key not in self.sessions:
                session = Session(game, now)
                self.sessions[key] = session
                log.info("Game started: %s", game.name)
                self._safe(self.listener.on_game_started, session)

        for key in list(self.sessions):
            if key not in running:
                session = self.sessions.pop(key)
                log.info("Game stopped: %s after %s", session.game.name, session.length(now))
                self._safe(self.listener.on_game_stopped, session, now)

        self._safe(self.listener.on_tick, list(self.sessions.values()), now)

    def _safe(self, fn: Callable, *args) -> None:
        try:
            fn(*args)
        except Exception:
            log.exception("Listener error in %s", getattr(fn, "__name__", fn))

    def _run(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self.interval)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="gameline-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval + 1)
