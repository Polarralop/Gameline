"""JSON-file persistence for app state (data/state.json).

The watcher thread and the Flask thread both touch state, so every load and
save goes through one lock. Writes are atomic (temp file + rename) so a
crash mid-save never leaves a corrupt file.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .models import Deadline, WorkingStyle

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "state.json"


@dataclass
class PlayedSession:
    """A finished gaming session, kept for recaps."""

    game: str
    start: datetime
    end: datetime

    @property
    def minutes(self) -> float:
        return max(0.0, (self.end - self.start).total_seconds() / 60)

    def to_dict(self) -> dict:
        return {"game": self.game, "start": self.start.isoformat(), "end": self.end.isoformat()}

    @classmethod
    def from_dict(cls, d: dict) -> PlayedSession:
        return cls(d["game"], datetime.fromisoformat(d["start"]), datetime.fromisoformat(d["end"]))


@dataclass
class State:
    deadlines: list[Deadline] = field(default_factory=list)
    working_style: WorkingStyle = field(default_factory=WorkingStyle)
    # App or process names the user tagged as games.
    tagged_games: list[str] = field(default_factory=list)
    # LLM backend chosen in Preferences ("" = use the GAMELINE_LLM default).
    llm_backend: str = ""
    # Deadlines view: "due" (chronological) or "subject" (grouped by course).
    view_sort: str = "due"
    show_completed: bool = False
    # Finished gaming sessions, for weekly/monthly recaps.
    sessions: list[PlayedSession] = field(default_factory=list)

    def get(self, deadline_id: str) -> Deadline | None:
        return next((d for d in self.deadlines if d.id == deadline_id), None)

    def to_dict(self) -> dict:
        return {
            "deadlines": [d.to_dict() for d in self.deadlines],
            "working_style": self.working_style.to_dict(),
            "tagged_games": self.tagged_games,
            "llm_backend": self.llm_backend,
            "view_sort": self.view_sort,
            "show_completed": self.show_completed,
            "sessions": [x.to_dict() for x in self.sessions],
        }

    @classmethod
    def from_dict(cls, d: dict) -> State:
        return cls(
            deadlines=[Deadline.from_dict(x) for x in d.get("deadlines", [])],
            working_style=WorkingStyle.from_dict(d.get("working_style", {})),
            tagged_games=list(d.get("tagged_games", [])),
            llm_backend=d.get("llm_backend", ""),
            view_sort=d.get("view_sort", "due"),
            show_completed=bool(d.get("show_completed", False)),
            sessions=[PlayedSession.from_dict(x) for x in d.get("sessions", [])],
        )


class Store:
    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        self.path = Path(path)
        self.lock = threading.RLock()

    def load(self) -> State:
        with self.lock:
            if not self.path.exists():
                return State()
            return State.from_dict(json.loads(self.path.read_text()))

    def save(self, state: State) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state.to_dict(), indent=2))
            os.replace(tmp, self.path)
