from datetime import datetime

import pytest

from gameline import syllabus
from gameline.llm.base import EstimatorLLM
from gameline.models import Deadline

NOW = datetime(2026, 10, 17, 12, 0)


class FakeLLM(EstimatorLLM):
    def complete_json(self, system, prompt, schema):
        assert "Today: 2026-10-17" in prompt
        return {"course": "CSCA48", "deadlines": [
            {"title": "CSCA48 Assignment 2", "due": "2026-10-22T23:59", "notes": "10%"},
            {"title": "CSCA48 Midterm", "due": "2026-10-28T18:00", "notes": "25%"},
            {"title": "CSCA48 Lab 5", "due": "TBA", "notes": ""},
        ]}


def test_propose_parses_and_skips_bad_dates():
    props = syllabus.propose("syllabus text " * 10, FakeLLM(), NOW)
    assert [p.title for p in props] == ["CSCA48 Assignment 2", "CSCA48 Midterm"]
    assert props[1].due == datetime(2026, 10, 28, 18, 0)


def test_duplicates_are_flagged():
    existing = [Deadline("CSCA48 A2", datetime(2026, 10, 22, 23, 59)),
                Deadline("Midterm - CSCA48", datetime(2026, 11, 30))]
    props = syllabus.mark_duplicates(syllabus.propose("x" * 100, FakeLLM(), NOW), existing)
    assert props[0].duplicate_of == "CSCA48 A2"  # similar title, same day
    assert props[1].duplicate_of is None  # different date, so not the same midterm


def test_unreadable_pdf_raises(tmp_path):
    bad = tmp_path / "x.pdf"
    bad.write_bytes(b"not a pdf")
    with pytest.raises(syllabus.SyllabusError):
        syllabus.extract_text(bad)
