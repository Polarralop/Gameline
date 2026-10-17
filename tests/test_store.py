from datetime import datetime

from gameline.models import Chunk, Deadline, Estimate, Style, WorkingStyle
from gameline.store import State, Store


def test_round_trip(tmp_path):
    store = Store(tmp_path / "state.json")
    d = Deadline(title="CSCA48 A2", due=datetime(2026, 10, 20, 23, 59), notes="linked lists")
    d.estimate = Estimate(
        effort_hours=6,
        importance=4,
        chunks=[Chunk("Read handout", 1, start=datetime(2026, 10, 18, 10)), Chunk("Code", 5, done=True)],
    )
    d.estimated_from = d.fingerprint()
    state = State(
        deadlines=[d],
        working_style=WorkingStyle(style=Style.SHORT_BURSTS, max_gaming_minutes=90),
        tagged_games=["Minecraft"],
    )
    store.save(state)

    loaded = store.load()
    assert loaded.to_dict() == state.to_dict()
    assert loaded.deadlines[0].estimate.remaining_hours == 1
    assert not loaded.deadlines[0].needs_estimate


def test_edit_triggers_reestimate():
    d = Deadline(title="Essay", due=datetime(2026, 10, 25))
    assert d.needs_estimate
    d.estimate = Estimate(effort_hours=3, importance=2)
    d.estimated_from = d.fingerprint()
    assert not d.needs_estimate
    d.due = datetime(2026, 10, 22)
    assert d.needs_estimate


def test_missing_file_gives_empty_state(tmp_path):
    assert Store(tmp_path / "nope.json").load().deadlines == []
