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
    assert w.sidebar.items[0][0].text() == "📋"


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
