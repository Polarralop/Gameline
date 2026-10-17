from gameline.context import AppContext
from gameline.dashboard import create_app
from gameline.llm.stub import StubLLM
from gameline.store import Store


def make(tmp_path):
    ctx = AppContext(Store(tmp_path / "s.json"))
    ctx._llm = StubLLM()
    return ctx, create_app(ctx).test_client()


def test_add_deadline_estimates_and_renders(tmp_path):
    ctx, client = make(tmp_path)
    r = client.post("/deadlines", data={"title": "MATA31 midterm", "due": "2030-01-10T09:00", "notes": ""})
    assert r.status_code == 302
    d = ctx.store.load().deadlines[0]
    assert d.estimate.effort_hours == 8
    page = client.get("/").get_data(as_text=True)
    assert "MATA31 midterm" in page and "Work block 1" in page


def test_seed_demo_has_one_at_risk(tmp_path):
    ctx, client = make(tmp_path)
    client.post("/demo/seed")
    assert ctx.status_line() == "1 deadline at risk"


def test_settings_save(tmp_path):
    ctx, client = make(tmp_path)
    client.post("/settings", data={"style": "long_sessions", "daily_work_hours": "3", "max_gaming_minutes": "90", "tagged_games": "Minecraft, Hades"})
    s = ctx.store.load()
    assert s.working_style.max_gaming_minutes == 90 and s.tagged_games == ["Minecraft", "Hades"]
