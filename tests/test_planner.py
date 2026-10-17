from datetime import datetime, timedelta

from gameline.models import Chunk, Deadline, Estimate, Style, WorkingStyle
from gameline.planner import assess, at_risk_deadlines, prep_hours_needed

NOW = datetime(2026, 10, 17, 12, 0)


def dl(title, days, hours, importance=3, chunks=None):
    d = Deadline(title=title, due=NOW + timedelta(days=days))
    d.estimate = Estimate(effort_hours=hours, importance=importance, chunks=chunks or [])
    return d


def test_on_track_is_silent():
    style = WorkingStyle(daily_work_hours=4)
    # 5 days * 4h = 20h available for 6h of work.
    assert not assess(dl("Essay", 5, 6), style, NOW).at_risk


def test_behind_is_flagged():
    style = WorkingStyle(daily_work_hours=4)
    # 1 day * 4h = 4h available for 6h of work.
    s = assess(dl("A2", 1, 6), style, NOW)
    assert s.at_risk and s.slack_hours < 0


def test_long_sessions_pad_more():
    d = dl("Project", 2, 5.5)  # 8h available
    assert not assess(d, WorkingStyle(style=Style.SHORT_BURSTS, daily_work_hours=4), NOW).at_risk
    assert assess(d, WorkingStyle(style=Style.LONG_SESSIONS, daily_work_hours=4), NOW).at_risk


def test_done_chunks_reduce_remaining():
    d = dl("Lab", 1, 6, chunks=[Chunk("a", 4, done=True), Chunk("b", 2)])
    assert assess(d, WorkingStyle(daily_work_hours=4), NOW).remaining_hours == 2


def test_sorted_tightest_first_and_past_ignored():
    style = WorkingStyle(daily_work_hours=4)
    risky = at_risk_deadlines([dl("Loose", 2, 7), dl("Tight", 1, 8), dl("Past", -1, 5)], style, NOW)
    assert [s.deadline.title for s in risky] == ["Tight", "Loose"]


def test_planned_chunk_overlap():
    c = Chunk("Q1", 2, start=NOW + timedelta(hours=1))
    s = assess(dl("A2", 3, 4, chunks=[c]), WorkingStyle(), NOW)
    assert s.planned_chunk is c


def test_prep_hours_horizon():
    assert prep_hours_needed([dl("Soon", 1, 5), dl("Later", 10, 9)], WorkingStyle(), NOW) == 5
