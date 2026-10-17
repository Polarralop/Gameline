"""Shared app objects that the menu bar, the watcher and the dashboard all use."""

from __future__ import annotations

import logging
import subprocess
import threading
from datetime import datetime, timedelta

from .clock import Clock
from .demo.fake_game import FAKE_GAME_NAME, build
from .detectors import GameDetector, default_detectors
from .estimator import estimate
from .llm import available_backends, default_backend, get_llm
from .models import Chunk, Deadline, Estimate, NotifyLevel, Style, WorkingStyle
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
        """The saved choice, unless it's no longer offered (the subscription
        option when hidden), then the default."""
        saved = self.store.load().llm_backend
        return saved if saved in available_backends() else default_backend()

    def set_backend(self, name: str) -> None:
        state = self.store.load()
        state.llm_backend = name
        self.store.save(state)

    def estimate_deadline(self, did: str) -> list[str]:
        """Estimate one deadline if it's new or edited. Returns error messages.

        The LLM call is slow, so it runs on a snapshot and the result is merged
        into freshly loaded state, so edits made meanwhile aren't overwritten.
        """
        d = self.store.load().get(did)
        if d is None or not d.needs_estimate:
            return []
        fingerprint = d.fingerprint()
        state = self.store.load()
        try:
            est = estimate(d, state.working_style, self.llm, self.clock.now())
        except Exception as exc:
            log.exception("Estimation failed")
            hint = " Log in to Claude in Preferences." if getattr(exc, "auth", False) else ""
            return [f"Couldn't estimate “{d.title}”: {exc}.{hint}"]
        with self.store.lock:
            state = self.store.load()
            current = state.get(did)
            if current and current.fingerprint() == fingerprint:  # still the same deadline
                current.estimate, current.estimated_from = est, fingerprint
                self.store.save(state)
        return []

    # --- user actions (the UI calls these; they are plain code so tests can too) ---

    def read_syllabus(self, path: str) -> list:
        """Proposed deadlines from a syllabus PDF (nothing is saved). Raises on failure."""
        from .syllabus import SyllabusError, read_syllabus

        try:
            return read_syllabus(path, self.llm, self.clock.now(), self.store.load().deadlines)
        except SyllabusError:
            raise
        except Exception as exc:
            hint = " Log in to Claude in Preferences." if getattr(exc, "auth", False) else ""
            raise SyllabusError(f"The AI couldn't read it: {exc}.{hint}") from exc

    def create_deadline(self, title: str, due: datetime, notes: str = "") -> str:
        """Save a deadline straight away (no estimate yet). Returns its id."""
        d = Deadline(title=title.strip(), due=due, notes=notes.strip())
        state = self.store.load()
        state.deadlines.append(d)
        self.store.save(state)
        return d.id

    def update_deadline(self, did: str, title: str, due: datetime, notes: str) -> bool:
        """Save edits straight away. Returns True if the deadline needs re-estimating."""
        state = self.store.load()
        d = state.get(did)
        if not d:
            return False
        d.title, d.due, d.notes = title.strip(), due, notes.strip()
        self.store.save(state)
        return d.needs_estimate

    def add_deadline(self, title: str, due: datetime, notes: str = "") -> list[str]:
        return self.estimate_deadline(self.create_deadline(title, due, notes))

    def edit_deadline(self, did: str, title: str, due: datetime, notes: str) -> list[str]:
        self.update_deadline(did, title, due, notes)
        return self.estimate_deadline(did)

    def complete_deadline(self, did: str, check_all: bool = False) -> None:
        state = self.store.load()
        d = state.get(did)
        if not d:
            return
        if check_all and d.estimate:
            for c in d.estimate.chunks:
                if not c.done:
                    c.done, c.done_at = True, self.clock.now()
        d.completed_at = self.clock.now()
        self.store.save(state)

    def reopen_deadline(self, did: str) -> None:
        state = self.store.load()
        d = state.get(did)
        if d:
            d.completed_at = None
            self.store.save(state)

    def set_view(self, sort: str | None = None, show_completed: bool | None = None) -> None:
        state = self.store.load()
        if sort is not None:
            state.view_sort = sort
        if show_completed is not None:
            state.show_completed = show_completed
        self.store.save(state)

    def finish_onboarding(self, style: WorkingStyle | None = None) -> None:
        """Save the onboarding answers (if any) and don't show it again."""
        with self.store.lock:
            state = self.store.load()
            if style is not None:
                style.repeat_minutes = state.working_style.repeat_minutes
                state.working_style = style
            state.onboarded = True
            self.store.save(state)

    def reset_onboarding(self) -> None:
        state = self.store.load()
        state.onboarded = False
        self.store.save(state)

    # --- danger zone -------------------------------------------------------

    def delete_all_deadlines(self) -> int:
        """Remove every deadline, open and completed (and the task history the
        recaps count as work). Returns how many were removed."""
        with self.store.lock:
            state = self.store.load()
            n = len(state.deadlines)
            state.deadlines = []
            self.store.save(state)
        return n

    def delete_game_history(self) -> int:
        """Forget recorded gaming sessions (what the recaps tally). Preferences,
        tagged games and deadlines are kept. Returns how many were removed."""
        with self.store.lock:
            state = self.store.load()
            n = len(state.sessions)
            state.sessions = []
            self.store.save(state)
        return n

    def delete_everything(self) -> None:
        self.store.save(State())

    def delete_deadline(self, did: str) -> None:
        state = self.store.load()
        state.deadlines = [d for d in state.deadlines if d.id != did]
        self.store.save(state)

    def set_chunk_done(self, did: str, index: int, done: bool) -> None:
        state = self.store.load()
        d = state.get(did)
        if d and d.estimate and 0 <= index < len(d.estimate.chunks):
            chunk = d.estimate.chunks[index]
            chunk.done = done
            chunk.done_at = self.clock.now() if done else None
            self.store.save(state)

    def save_settings(self, style: WorkingStyle) -> None:
        state = self.store.load()
        style.notify_level = state.working_style.notify_level  # saved on its own, below
        state.working_style = style
        self.store.save(state)

    def set_notify_level(self, level: NotifyLevel) -> None:
        state = self.store.load()
        state.working_style.notify_level = level
        self.store.save(state)

    def add_tagged_game(self, name: str) -> bool:
        """Returns False if empty or already in the list (case-insensitive)."""
        name = name.strip()
        state = self.store.load()
        if not name or name.lower() in {g.lower() for g in state.tagged_games}:
            return False
        state.tagged_games.append(name)
        self.store.save(state)
        return True

    def remove_tagged_game(self, name: str) -> None:
        state = self.store.load()
        state.tagged_games = [g for g in state.tagged_games if g != name]
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
        history, sessions = _demo_history(now)
        state = self.store.load()
        state.deadlines = [a2, essay, *history]
        state.sessions = sessions
        state.working_style = WorkingStyle(style=Style.SHORT_BURSTS, daily_work_hours=4, max_gaming_minutes=120)
        self.store.save(state)


def _demo_history(now: datetime) -> tuple[list[Deadline], list]:
    """Five weeks of finished work and gaming, so the Recap page has something
    to show in the demo. Deterministic, so the demo looks the same every time."""
    import random

    from .store import PlayedSession

    rng = random.Random(48)
    done: list[Deadline] = []
    specs = [
        ("CSCA48 Assignment 1", 33, [("Read handout", 1), ("Q1-Q2", 3), ("Q3-Q4", 3), ("Test and submit", 1)]),
        ("MATA31 Quiz 3 prep", 26, [("Review notes", 1.5), ("Practice set", 2)]),
        ("WSTC02 Response paper", 19, [("Read article", 1), ("Outline", 1), ("Draft", 2.5), ("Edit", 1)]),
        ("CSCA48 Lab 4", 12, [("Lab exercises", 2)]),
        ("MATA31 Problem Set 4", 2, [("Questions 1-5", 2.5), ("Questions 6-10", 3), ("Write up", 1)]),
    ]
    for title, days_ago, tasks in specs:
        due = (now - timedelta(days=days_ago)).replace(hour=23, minute=59)
        d = Deadline(title, due)
        d.estimate = Estimate(
            effort_hours=sum(h for _, h in tasks), importance=3, rationale="",
            chunks=[
                Chunk(name, hours, done=True,
                      done_at=(due - timedelta(days=len(tasks) - i, hours=rng.randint(2, 8))).replace(minute=0))
                for i, (name, hours) in enumerate(tasks)
            ],
        )
        d.estimated_from = d.fingerprint()
        d.completed_at = due - timedelta(hours=3)
        done.append(d)

    sessions = []
    games = [("Factorio", 0.45), ("Slay the Spire 2", 0.35), ("Hades II", 0.2)]
    for days_ago in range(35, 0, -1):
        if rng.random() < 0.35:
            continue  # a night off
        game = rng.choices([g for g, _ in games], weights=[w for _, w in games])[0]
        start = (now - timedelta(days=days_ago)).replace(hour=rng.choice([19, 20, 21, 22]), minute=0)
        sessions.append(PlayedSession(game, start, start + timedelta(minutes=rng.choice([45, 60, 90, 120, 150, 180]))))
    return done, sessions
