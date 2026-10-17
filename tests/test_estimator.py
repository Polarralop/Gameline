from datetime import datetime

from gameline.estimator import estimate_pending, parse_estimate
from gameline.llm import get_llm
from gameline.models import Deadline
from gameline.store import State


def test_estimate_pending_only_touches_new_or_edited():
    state = State(deadlines=[Deadline("CSCA48 midterm", datetime(2026, 10, 24))])
    llm = get_llm("stub")
    assert len(estimate_pending(state, llm)) == 1
    assert state.deadlines[0].estimate.effort_hours == 8
    assert estimate_pending(state, llm) == []  # unchanged -> no LLM call
    state.deadlines[0].notes = "covers weeks 1-6"
    assert len(estimate_pending(state, llm)) == 1


def test_parse_clamps_and_tolerates_bad_dates():
    est = parse_estimate(
        {"effort_hours": 3, "importance": 9, "chunks": [{"title": "a", "hours": 3, "start": "soon"}]}
    )
    assert est.importance == 5
    assert est.chunks[0].start is None
