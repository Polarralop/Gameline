"""Syllabus reader: PDF -> text -> LLM -> proposed deadlines.

Reuses the estimator's LLM interface, so it works with any backend. The user
reviews the proposals before anything is added; ones that look like
deadlines already on the list are flagged and left unticked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from pypdf import PdfReader

from .llm.base import EstimatorLLM
from .models import Deadline

MAX_CHARS = 60_000  # plenty for a syllabus; keeps the prompt bounded

SYSTEM = (
    "You extract graded deadlines from a university course syllabus: assignments, labs, "
    "quizzes, tests, midterms, exams, projects, presentations and other submissions. "
    "Skip readings, lectures and office hours. Give each a short title that starts with "
    "the course code if there is one (e.g. 'CSCA48 Assignment 2'). Resolve dates to the "
    "academic term the syllabus describes, relative to today's date. If no time is given, "
    "use 23:59. Put the weight and any useful details in notes. If a date is genuinely "
    "unknown (e.g. 'TBA'), leave it out. Return only the structured result."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "course": {"type": "string", "description": "Course code or name, if found."},
        "deadlines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "due": {"type": "string", "description": "ISO 8601 local datetime, e.g. 2026-10-20T23:59"},
                    "notes": {"type": "string", "description": "Weight and details, one short line."},
                },
                "required": ["title", "due", "notes"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["course", "deadlines"],
    "additionalProperties": False,
}


class SyllabusError(RuntimeError):
    pass


@dataclass
class Proposal:
    title: str
    due: datetime
    notes: str = ""
    # Title of an existing deadline this one seems to duplicate, if any.
    duplicate_of: str | None = None
    # Already past when the syllabus was read (shown, but unticked).
    past: bool = False

    @property
    def suggested(self) -> bool:
        return self.duplicate_of is None and not self.past


def extract_text(path: str | Path) -> str:
    try:
        reader = PdfReader(str(path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        raise SyllabusError(f"Couldn't open that PDF ({exc.__class__.__name__}).") from exc
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) < 40:
        raise SyllabusError("That PDF has no readable text. It may be a scanned image.")
    return text[:MAX_CHARS]


def propose(text: str, llm: EstimatorLLM, now: datetime) -> list[Proposal]:
    prompt = f"Today: {now.date().isoformat()}\n\nSyllabus text:\n{text}"
    data = llm.complete_json(SYSTEM, prompt, SCHEMA)
    out = []
    for item in data.get("deadlines", []):
        try:
            due = datetime.fromisoformat(str(item["due"])).replace(tzinfo=None, second=0, microsecond=0)
        except (KeyError, ValueError):
            continue
        title = str(item.get("title", "")).strip()
        if title:
            out.append(Proposal(title=title, due=due, notes=str(item.get("notes", "")).strip()))
    return sorted(out, key=lambda p: p.due)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def find_duplicate(p: Proposal, existing: list[Deadline]) -> Deadline | None:
    """Same-ish title, or a similar title due within a day of it."""
    for d in existing:
        ratio = SequenceMatcher(None, _norm(p.title), _norm(d.title)).ratio()
        close_in_time = abs((p.due - d.due).total_seconds()) <= 36 * 3600
        if ratio >= 0.85 or (close_in_time and ratio >= 0.6):
            return d
    return None


def mark_duplicates(proposals: list[Proposal], existing: list[Deadline]) -> list[Proposal]:
    for p in proposals:
        dup = find_duplicate(p, existing)
        p.duplicate_of = dup.title if dup else None
    return proposals


def read_syllabus(path: str | Path, llm: EstimatorLLM, now: datetime, existing: list[Deadline]) -> list[Proposal]:
    proposals = mark_duplicates(propose(extract_text(path), llm, now), existing)
    for p in proposals:
        p.past = p.due < now
    return proposals
