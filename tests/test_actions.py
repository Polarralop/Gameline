from datetime import datetime

from gameline.context import AppContext
from gameline.llm.stub import StubLLM
from gameline.models import Style, WorkingStyle
from gameline.store import Store


def make(tmp_path):
    return AppContext(Store(tmp_path / "s.json"), llm=StubLLM())


def test_add_edit_delete_deadline(tmp_path):
    ctx = make(tmp_path)
    assert ctx.add_deadline("MATA31 midterm", datetime(2030, 1, 10, 9)) == []
    d = ctx.store.load().deadlines[0]
    assert d.estimate.effort_hours == 8
    ctx.edit_deadline(d.id, "MATA31 quiz", d.due, "")
    assert ctx.store.load().deadlines[0].estimate.effort_hours == 2
    ctx.set_chunk_done(d.id, 0, True)
    assert ctx.store.load().deadlines[0].estimate.chunks[0].done
    ctx.delete_deadline(d.id)
    assert ctx.store.load().deadlines == []


def test_seed_demo_has_one_at_risk(tmp_path):
    ctx = make(tmp_path)
    ctx.seed_demo_data()
    assert ctx.status_line() == "1 deadline at risk"


def test_save_settings(tmp_path):
    ctx = make(tmp_path)
    ctx.save_settings(WorkingStyle(style=Style.LONG_SESSIONS, max_gaming_minutes=90), ["Minecraft", " ", "Hades"])
    s = ctx.store.load()
    assert s.working_style.max_gaming_minutes == 90 and s.tagged_games == ["Minecraft", "Hades"]
