"""Shared app objects that the menu bar, the watcher and the dashboard all use."""

from __future__ import annotations

import logging
import subprocess
import threading
from datetime import datetime, timedelta

from .clock import Clock
from .demo.fake_game import FAKE_GAME_NAME, build
from .detectors import GameDetector, default_detectors
from .estimator import estimate_pending
from .llm import default_backend, get_llm
from .models import Chunk, Deadline, Estimate, Style, WorkingStyle
from .planner import at_risk_deadlines
from .store import State, Store

log = logging.getLogger(__name__)

DEMO_SPEED = 360.0  # 1 real second = 6 app minutes


class AppContext:
    def __init__(self, store: Store | None = None, llm=None) -> None:
        self.store = store or Store()
        self.clock = Clock()
        # A fixed llm (tests) wins; otherwise it follows the Preferences choice.
        self._fixed_llm = llm
        self._llm = None
        self._llm_name = None
        self._fake_game: subprocess.Popen | None = None
        self._lock = threading.Lock()

    # Detectors are rebuilt each poll so newly tagged games apply immediately.
    def detectors(self) -> list[GameDetector]:
        tagged = self.store.load().tagged_games + [FAKE_GAME_NAME]
        return default_detectors(tagged_names=tagged)

    @property
    def llm(self):
        if self._fixed_llm is not None:
            return self._fixed_llm
        name = self.backend_name()
        if self._llm is None or name != self._llm_name:
            self._llm, self._llm_name = get_llm(name), name
        return self._llm

    def backend_name(self) -> str:
        return self.store.load().llm_backend or default_backend()

    def set_backend(self, name: str) -> None:
        state = self.store.load()
        state.llm_backend = name
        self.store.save(state)

    def save_and_estimate(self, state: State) -> list[str]:
        """Persist, then estimate any new or edited deadlines. Returns error messages."""
        errors = []
        try:
            estimate_pending(state, self.llm, self.clock.now())
        except Exception as exc:
            log.exception("Estimation failed")
            hint = " Log in to Claude in Preferences." if getattr(exc, "auth", False) else ""
            errors.append(f"Estimate failed: {exc}.{hint} It will retry on the next save.")
        self.store.save(state)
        return errors

    # --- user actions (the UI calls these; they are plain code so tests can too) ---

    def add_deadline(self, title: str, due: datetime, notes: str = "") -> list[str]:
        state = self.store.load()
        state.deadlines.append(Deadline(title=title.strip(), due=due, notes=notes.strip()))
        return self.save_and_estimate(state)

    def edit_deadline(self, did: str, title: str, due: datetime, notes: str) -> list[str]:
        state = self.store.load()
        d = state.get(did)
        if not d:
            return []
        d.title, d.due, d.notes = title.strip(), due, notes.strip()
        return self.save_and_estimate(state)

    def delete_deadline(self, did: str) -> None:
        state = self.store.load()
        state.deadlines = [d for d in state.deadlines if d.id != did]
        self.store.save(state)

    def set_chunk_done(self, did: str, index: int, done: bool) -> None:
        state = self.store.load()
        d = state.get(did)
        if d and d.estimate and 0 <= index < len(d.estimate.chunks):
            d.estimate.chunks[index].done = done
            self.store.save(state)

    def save_settings(self, style: WorkingStyle, tagged_games: list[str]) -> None:
        state = self.store.load()
        state.working_style = style
        state.tagged_games = [t.strip() for t in tagged_games if t.strip()]
        self.store.save(state)

    def status_line(self) -> str:
        state = self.store.load()
        risky = at_risk_deadlines(state.deadlines, state.working_style, self.clock.now())
        if not risky:
            return "On track"
        return f"{len(risky)} deadline{'s' if len(risky) > 1 else ''} at risk"

    # --- demo mode -----------------------------------------------------------

    @property
    def demo_mode(self) -> bool:
        return self.clock.speed > 1

    def set_demo_mode(self, on: bool) -> None:
        self.clock.set_speed(DEMO_SPEED if on else 1.0)

    @property
    def fake_game_running(self) -> bool:
        return self._fake_game is not None and self._fake_game.poll() is None

    def start_fake_game(self) -> None:
        with self._lock:
            if not self.fake_game_running:
                self._fake_game = subprocess.Popen([str(build())])

    def stop_fake_game(self) -> None:
        with self._lock:
            if self.fake_game_running:
                self._fake_game.terminate()
                self._fake_game.wait(timeout=5)
            self._fake_game = None

    def seed_demo_data(self) -> None:
        """Replace state with a believable student week: one deadline at risk, one fine."""
        now = self.clock.now().replace(second=0, microsecond=0)

        def chunks(spec):
            return [Chunk(t, h, start=now + timedelta(hours=off)) for t, h, off in spec]

        a2 = Deadline("CSCA48 Assignment 2", now + timedelta(days=1, hours=2), "Linked lists and recursion, 4 questions")
        a2.estimate = Estimate(
            effort_hours=9,
            importance=4,
            rationale="Four coding questions plus debugging; padded 20%.",
            chunks=chunks([("Q1 + Q2", 3, 0.5), ("Q3 recursion", 3, 18), ("Q4 + tests", 3, 22)]),
        )
        essay = Deadline("WSTC02 reflection essay", now + timedelta(days=6), "1000 words")
        essay.estimate = Estimate(
            effort_hours=4,
            importance=2,
            rationale="Short reflective piece.",
            chunks=chunks([("Outline", 1, 48), ("Draft", 2, 72), ("Edit", 1, 96)]),
        )
        for d in (a2, essay):
            d.estimated_from = d.fingerprint()
        state = self.store.load()
        state.deadlines = [a2, essay]
        state.working_style = WorkingStyle(style=Style.SHORT_BURSTS, daily_work_hours=4, max_gaming_minutes=120)
        self.store.save(state)
