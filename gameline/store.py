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
from pathlib import Path

from .models import Deadline, WorkingStyle

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "state.json"


@dataclass
class State:
    deadlines: list[Deadline] = field(default_factory=list)
    working_style: WorkingStyle = field(default_factory=WorkingStyle)
    # App or process names the user tagged as games.
    tagged_games: list[str] = field(default_factory=list)
    # LLM backend chosen in Preferences ("" = use the GAMELINE_LLM default).
    llm_backend: str = ""

    def get(self, deadline_id: str) -> Deadline | None:
        return next((d for d in self.deadlines if d.id == deadline_id), None)

    def to_dict(self) -> dict:
        return {
            "deadlines": [d.to_dict() for d in self.deadlines],
            "working_style": self.working_style.to_dict(),
            "tagged_games": self.tagged_games,
            "llm_backend": self.llm_backend,
        }

    @classmethod
    def from_dict(cls, d: dict) -> State:
        return cls(
            deadlines=[Deadline.from_dict(x) for x in d.get("deadlines", [])],
            working_style=WorkingStyle.from_dict(d.get("working_style", {})),
            tagged_games=list(d.get("tagged_games", [])),
            llm_backend=d.get("llm_backend", ""),
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
