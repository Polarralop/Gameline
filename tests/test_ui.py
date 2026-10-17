import os
from datetime import datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from gameline.context import AppContext  # noqa: E402
from gameline.llm.claude_cli import AccountStatus  # noqa: E402
from gameline.store import Store  # noqa: E402
from gameline.ui.window import ConfirmModal, DeadlineModal, MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_modal_saves_values_and_closes(qapp):
    host = QtWidgets.QWidget()
    host.resize(1000, 600)
    saved = []
    modal = DeadlineModal(host, datetime(2026, 10, 17, 12, 0), lambda *v: saved.append(v))
    assert modal.parent() is host and not modal.isWindow()  # in-window, not a new window
    modal.title.setText("A2")
    modal.due.setDateTime(modal.due.dateTime().fromString("2026-10-20T23:59", "yyyy-MM-ddTHH:mm"))
    modal._save()
    assert saved == [("A2", datetime(2026, 10, 20, 23, 59), "")]


def test_modal_requires_title(qapp):
    host = QtWidgets.QWidget()
    saved = []
    DeadlineModal(host, datetime(2026, 10, 17), lambda *v: saved.append(v))._save()
    assert saved == []


def test_window_renders_seeded_week(qapp, tmp_path):
    ctx = AppContext(Store(tmp_path / "s.json"))
    ctx.seed_demo_data()
    w = MainWindow(ctx, lambda: [])
    assert w.cards.count() == 3  # two cards + stretch
    assert w.status_pill.text() == "1 deadline at risk"


def test_sidebar_switches_pages_and_collapses(qapp, tmp_path):
    w = MainWindow(AppContext(Store(tmp_path / "s.json")), lambda: [])
    w.account_checker = lambda: AccountStatus(installed=False)  # don't call the real CLI
    assert w.page_title.text() == "Deadlines"
    w.sidebar.items[1][0].click()
    assert w.stack.currentIndex() == 1 and w.page_title.text() == "Demo"
    w.sidebar.items[2][0].click()
    assert w.page_title.text() == "Preferences"
    lay = w.sidebar.lay
    assert lay.indexOf(w.sidebar.items[2][0]) == lay.count() - 1  # pinned to the bottom
    w.sidebar.toggle()
    w.sidebar.anim.setCurrentTime(w.sidebar.anim.duration())
    assert w.sidebar.maximumWidth() == w.sidebar.COLLAPSED
    assert w.sidebar.items[0][0].text() == "" and not w.sidebar.items[0][0].icon().isNull()


def test_delete_asks_in_modal_then_deletes(qapp, tmp_path):
    ctx = AppContext(Store(tmp_path / "s.json"))
    ctx.seed_demo_data()
    w = MainWindow(ctx, lambda: [])
    modal = w.delete_deadline(ctx.store.load().deadlines[0])
    assert isinstance(modal, ConfirmModal) and not modal.isWindow()
    assert len(ctx.store.load().deadlines) == 2  # nothing deleted until confirmed
    modal.confirm_btn.click()
    assert len(ctx.store.load().deadlines) == 1


def test_claude_button_reflects_status(qapp, tmp_path):
    w = MainWindow(AppContext(Store(tmp_path / "s.json")), lambda: [])
    w._show_claude(AccountStatus(installed=True, logged_in=True, working=True, email="me@x.ca", plan="pro"))
    assert "Logged in" in w.claude_btn.text() and w.claude_btn.property("tone") == "ok"
    w._show_claude(AccountStatus(installed=True, logged_in=True, working=False, message="OAuth session expired"))
    assert w.claude_btn.text() == "Log in to Claude" and "Session expired" in w.claude_status.text()
    w._show_claude(AccountStatus(installed=False))
    assert not w.claude_btn.isEnabled()


def test_new_deadline_shows_pending_then_estimates(qapp, tmp_path):
    import time

    from gameline.llm.stub import StubLLM

    ctx = AppContext(Store(tmp_path / "s.json"), llm=StubLLM())
    w = MainWindow(ctx, lambda: [])
    did = ctx.create_deadline("MATA31 midterm", datetime(2030, 1, 10, 9))
    w.start_estimate(did)
    assert did in w.pending
    deadline = time.time() + 5
    while w.pending and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert not w.pending
    assert ctx.store.load().get(did).estimate.effort_hours == 8
    assert w.toaster.toasts  # "Estimated …" toast is showing


def test_toast_auto_dismisses(qapp, tmp_path):
    import time

    w = MainWindow(AppContext(Store(tmp_path / "s.json")), lambda: [])
    w.toast("Hello", ms=50)
    assert len(w.toaster.toasts) == 1
    end = time.time() + 2
    while w.toaster.toasts and time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)
    assert w.toaster.toasts == []


def test_collapse_arrow_hides_tasks(qapp, tmp_path):
    from gameline.ui.window import DeadlineCard, TaskRow

    ctx = AppContext(Store(tmp_path / "s.json"))
    ctx.seed_demo_data()
    w = MainWindow(ctx, lambda: [])
    did = ctx.store.load().deadlines[0].id

    def first_card():
        return next(w.cards.itemAt(i).widget() for i in range(w.cards.count())
                    if isinstance(w.cards.itemAt(i).widget(), DeadlineCard))

    before = dict(w.card_widgets)
    card = first_card()
    assert card.details.isVisibleTo(card)
    w.toggle_collapsed(did)
    assert not card.details.isVisibleTo(card) and card.summary.text() == "0 of 3 tasks done"
    rows = card.findChildren(TaskRow)
    rows[0].box.click()  # tick a task: saved, and updated without rebuilding any card
    assert ctx.store.load().get(did).estimate.chunks[0].done
    assert w.card_widgets == before


def test_interrupt_level_needs_confirmation(qapp, tmp_path):
    from gameline.models import NotifyLevel
    from gameline.ui.window import ConfirmModal

    ctx = AppContext(Store(tmp_path / "s.json"))
    w = MainWindow(ctx, lambda: [])
    w.account_checker = lambda: AccountStatus(installed=False)
    box = w.notify_box
    box.setCurrentIndex(box.findData(NotifyLevel.INTERRUPT))
    modal = w.centralWidget().findChildren(ConfirmModal)[-1]
    modal.close_modal()  # cancel
    assert box.currentData() == NotifyLevel.NORMAL
    assert ctx.store.load().working_style.notify_level == NotifyLevel.NORMAL
    box.setCurrentIndex(box.findData(NotifyLevel.INTERRUPT))
    w.centralWidget().findChildren(ConfirmModal)[-1].confirm_btn.click()
    assert ctx.store.load().working_style.notify_level == NotifyLevel.INTERRUPT
    box.setCurrentIndex(box.findData(NotifyLevel.OFF))
    assert not w.max_minutes.isEnabled() and not w.repeat_minutes.isEnabled()


def test_game_list_add_and_remove(qapp, tmp_path):
    ctx = AppContext(Store(tmp_path / "s.json"))
    w = MainWindow(ctx, lambda: [])
    gl = w.game_list
    gl.input.setText("Minecraft")
    gl._add()
    gl.input.setText("Hades")
    gl.input.returnPressed.emit()
    assert ctx.store.load().tagged_games == ["Minecraft", "Hades"] and gl.input.text() == ""
    w._remove_game("Minecraft")
    assert ctx.store.load().tagged_games == ["Hades"]


def test_notifications_help_badge(qapp, tmp_path):
    w = MainWindow(AppContext(Store(tmp_path / "s.json")), lambda: [])
    badge = next(l for l in w.findChildren(QtWidgets.QWidget) if l.objectName() == "help")
    for level in ("No notifications", "Standard", "Interrupting"):
        assert level in badge.toolTip()


def test_bulk_add_flow(qapp, tmp_path):
    import time

    from gameline.syllabus import Proposal
    from gameline.ui.window import SyllabusModal

    ctx = AppContext(Store(tmp_path / "s.json"))
    ctx.create_deadline("CSCA48 A2", datetime(2026, 10, 22, 23, 59))
    proposals = [Proposal("CSCA48 Assignment 2", datetime(2026, 10, 22, 23, 59), "10%", duplicate_of="CSCA48 A2"),
                 Proposal("CSCA48 Midterm", datetime(2026, 10, 28, 18, 0), "25%")]
    ctx.read_syllabus = lambda path: proposals
    w = MainWindow(ctx, lambda: [])
    w.start_estimate = lambda did: None  # don't call an LLM here
    modal = w.bulk_add("/tmp/csca48.pdf")
    assert isinstance(modal, SyllabusModal)
    end = time.time() + 5
    while not hasattr(modal, "checks") and time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)
    assert [b.isChecked() for b in modal.checks] == [False, True]  # duplicate starts unticked
    assert modal.add_btn.text() == "Add 1 deadline"
    modal.add_btn.click()
    titles = [d.title for d in ctx.store.load().deadlines]
    assert titles == ["CSCA48 A2", "CSCA48 Midterm"]
