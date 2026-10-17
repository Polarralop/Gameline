from datetime import datetime

from gameline.context import AppContext
from gameline.llm.stub import StubLLM
from gameline.models import NotifyLevel, Style, WorkingStyle
from gameline.store import State, Store


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


def test_save_settings_keeps_notify_level(tmp_path):
    ctx = make(tmp_path)
    ctx.set_notify_level(NotifyLevel.OFF)
    ctx.save_settings(WorkingStyle(style=Style.LONG_SESSIONS, max_gaming_minutes=90))
    s = ctx.store.load()
    assert s.working_style.max_gaming_minutes == 90 and s.working_style.notify_level == NotifyLevel.OFF


def test_tagged_games_add_remove(tmp_path):
    ctx = make(tmp_path)
    assert ctx.add_tagged_game(" Minecraft ")
    assert not ctx.add_tagged_game("minecraft")  # duplicate
    assert not ctx.add_tagged_game("  ")
    ctx.add_tagged_game("Hades")
    ctx.remove_tagged_game("Minecraft")
    assert ctx.store.load().tagged_games == ["Hades"]


def test_estimate_does_not_overwrite_edits_made_meanwhile(tmp_path):
    class SlowEditLLM(StubLLM):
        def complete_json(self, system, prompt, schema):
            # Simulate the user editing the deadline while the AI is thinking.
            s = ctx.store.load()
            s.deadlines[0].notes = "changed"
            ctx.store.save(s)
            return super().complete_json(system, prompt, schema)

    ctx = AppContext(Store(tmp_path / "s.json"), llm=SlowEditLLM())
    did = ctx.create_deadline("Essay", datetime(2030, 1, 10))
    ctx.estimate_deadline(did)
    d = ctx.store.load().get(did)
    assert d.notes == "changed" and d.estimate is None  # stale estimate discarded


def test_complete_and_reopen(tmp_path):
    ctx = make(tmp_path)
    ctx.seed_demo_data()
    a2 = ctx.store.load().deadlines[0]
    assert ctx.status_line() == "1 deadline at risk"
    ctx.complete_deadline(a2.id, check_all=True)
    d = ctx.store.load().get(a2.id)
    assert d.completed and d.all_tasks_done
    assert ctx.status_line() == "On track"  # completed deadlines don't count as at risk
    ctx.reopen_deadline(a2.id)
    assert not ctx.store.load().get(a2.id).completed


def test_danger_zone(tmp_path):
    ctx = make(tmp_path)
    ctx.seed_demo_data()
    ctx.add_tagged_game("Minecraft")
    assert ctx.delete_all_deadlines() > 0
    s = ctx.store.load()
    assert s.deadlines == [] and s.tagged_games == ["Minecraft"] and s.sessions  # data kept
    ctx.seed_demo_data()
    ctx.set_notify_level(NotifyLevel.OFF)
    assert ctx.delete_game_history() > 0
    s = ctx.store.load()
    assert s.deadlines and not s.sessions and s.tagged_games == ["Minecraft"]
    assert s.working_style.notify_level == NotifyLevel.OFF  # preferences kept
    ctx.delete_everything()
    assert ctx.store.load().to_dict() == State().to_dict()
