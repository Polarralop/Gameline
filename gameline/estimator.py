"""Turn a deadline into an effort estimate and chunk plan via the LLM.

Called only when a deadline is added or edited (Deadline.needs_estimate),
never from the polling loop.
"""

from __future__ import annotations

from datetime import datetime

from .llm.base import EstimatorLLM
from .models import Chunk, Deadline, Estimate, WorkingStyle
from .store import State

SYSTEM = (
    "You are a realistic study and work planner for a university student. "
    "Estimate how long a task really takes (students underestimate; pad 20%), "
    "how important it is, and split it into work chunks that fit the student's "
    "working style. Schedule chunks between now and the due date, leaving a "
    "buffer before the deadline. Return only the structured result."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "effort_hours": {"type": "number", "description": "Total hours of focused work."},
        "importance": {"type": "integer", "minimum": 1, "maximum": 5},
        "rationale": {"type": "string", "description": "One sentence on the estimate."},
        "chunks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "hours": {"type": "number"},
                    "start": {"type": "string", "description": "ISO 8601 local datetime."},
                },
                "required": ["title", "hours"],
            },
        },
    },
    "required": ["effort_hours", "importance", "chunks"],
}

_CHUNK_HINT = {
    "short_bursts": "chunks of 0.5-1.5 hours",
    "long_sessions": "chunks of 2.5-4 hours",
    "mixed": "chunks of 1-2.5 hours",
}


def build_prompt(deadline: Deadline, style: WorkingStyle, now: datetime) -> str:
    return (
        f"Now: {now.isoformat(timespec='minutes')}\n"
        f"Task: {deadline.title}\n"
        f"Due: {deadline.due.isoformat(timespec='minutes')}\n"
        f"Details: {deadline.notes or '(none)'}\n"
        f"Working style: {style.style.value}, prefers {_CHUNK_HINT[style.style.value]}, "
        f"about {style.daily_work_hours:g} hours of work per day."
    )


def parse_estimate(data: dict) -> Estimate:
    chunks = []
    for c in data.get("chunks", []):
        start = None
        if c.get("start"):
            try:
                start = datetime.fromisoformat(c["start"]).replace(tzinfo=None)
            except ValueError:
                pass
        chunks.append(Chunk(title=str(c["title"]), hours=float(c["hours"]), start=start))
    return Estimate(
        effort_hours=float(data["effort_hours"]),
        importance=max(1, min(5, int(data["importance"]))),
        rationale=str(data.get("rationale", "")),
        chunks=chunks,
    )


def estimate(deadline: Deadline, style: WorkingStyle, llm: EstimatorLLM, now: datetime | None = None) -> Estimate:
    data = llm.complete_json(SYSTEM, build_prompt(deadline, style, now or datetime.now()), SCHEMA)
    return parse_estimate(data)


def estimate_pending(state: State, llm: EstimatorLLM, now: datetime | None = None) -> list[Deadline]:
    """Estimate every new or edited deadline in place. Returns the ones updated."""
    updated = []
    for d in state.deadlines:
        if d.needs_estimate:
            d.estimate = estimate(d, state.working_style, llm, now)
            d.estimated_from = d.fingerprint()
            updated.append(d)
    return updated
