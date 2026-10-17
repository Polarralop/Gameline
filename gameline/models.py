"""Core data: deadlines, the user's working style, and LLM estimates.

Plain dataclasses with to_dict/from_dict so state.json stays readable and
the UI can build them directly.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum


class NotifyLevel(str, Enum):
    OFF = "off"  # no reminders or alerts; the menu bar dot still shows risk
    NORMAL = "normal"  # desktop notifications
    INTERRUPT = "interrupt"  # long-session alerts also bring the Gameline window forward


class Style(str, Enum):
    SHORT_BURSTS = "short_bursts"  # many ~1h blocks
    LONG_SESSIONS = "long_sessions"  # fewer 3h+ blocks
    MIXED = "mixed"


@dataclass
class WorkingStyle:
    style: Style = Style.MIXED
    # Hours per day the user is realistically willing to work on deadlines.
    daily_work_hours: float = 4.0
    # Gaming session length after which a long-session alert fires.
    max_gaming_minutes: int = 120
    # After the limit, the break alert repeats this often while you keep playing.
    repeat_minutes: int = 60
    notify_level: NotifyLevel = NotifyLevel.NORMAL

    def to_dict(self) -> dict:
        # Style(...) / NotifyLevel(...) also accept plain strings (Qt hands enum data back as str).
        return {**asdict(self), "style": Style(self.style).value, "notify_level": NotifyLevel(self.notify_level).value}

    @classmethod
    def from_dict(cls, d: dict) -> WorkingStyle:
        return cls(
            style=Style(d.get("style", Style.MIXED.value)),
            daily_work_hours=float(d.get("daily_work_hours", 4.0)),
            max_gaming_minutes=int(d.get("max_gaming_minutes", 120)),
            repeat_minutes=int(d.get("repeat_minutes", 60)),
            notify_level=NotifyLevel(d.get("notify_level", NotifyLevel.NORMAL.value)),
        )


@dataclass
class Chunk:
    """One planned work block from the LLM's chunk plan."""

    title: str
    hours: float
    # Suggested start, if the plan scheduled one.
    start: datetime | None = None
    done: bool = False


@dataclass
class Estimate:
    effort_hours: float
    importance: int  # 1 (low) to 5 (critical)
    chunks: list[Chunk] = field(default_factory=list)
    rationale: str = ""

    @property
    def remaining_hours(self) -> float:
        if not self.chunks:
            return self.effort_hours
        return sum(c.hours for c in self.chunks if not c.done)


@dataclass
class Deadline:
    title: str
    due: datetime
    notes: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    estimate: Estimate | None = None
    # Fingerprint of the fields the estimate was made from; re-estimate when it changes.
    estimated_from: str | None = None

    def fingerprint(self) -> str:
        return f"{self.title}|{self.due.isoformat()}|{self.notes}"

    @property
    def needs_estimate(self) -> bool:
        return self.estimate is None or self.estimated_from != self.fingerprint()

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "title": self.title,
            "due": self.due.isoformat(),
            "notes": self.notes,
            "estimated_from": self.estimated_from,
            "estimate": None,
        }
        if self.estimate:
            e = self.estimate
            d["estimate"] = {
                "effort_hours": e.effort_hours,
                "importance": e.importance,
                "rationale": e.rationale,
                "chunks": [
                    {
                        "title": c.title,
                        "hours": c.hours,
                        "start": c.start.isoformat() if c.start else None,
                        "done": c.done,
                    }
                    for c in e.chunks
                ],
            }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Deadline:
        est = None
        if d.get("estimate"):
            e = d["estimate"]
            est = Estimate(
                effort_hours=float(e["effort_hours"]),
                importance=int(e["importance"]),
                rationale=e.get("rationale", ""),
                chunks=[
                    Chunk(
                        title=c["title"],
                        hours=float(c["hours"]),
                        start=datetime.fromisoformat(c["start"]) if c.get("start") else None,
                        done=bool(c.get("done", False)),
                    )
                    for c in e.get("chunks", [])
                ],
            )
        return cls(
            id=d["id"],
            title=d["title"],
            due=datetime.fromisoformat(d["due"]),
            notes=d.get("notes", ""),
            estimate=est,
            estimated_from=d.get("estimated_from"),
        )
