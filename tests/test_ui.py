import os
from datetime import datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from gameline.context import AppContext  # noqa: E402
from gameline.store import Store  # noqa: E402
from gameline.ui.window import DeadlineModal, MainWindow  # noqa: E402


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
    assert w.page_title.text() == "Deadlines"
    w.sidebar.items[2][0].click()
    assert w.stack.currentIndex() == 2 and w.page_title.text() == "Demo"
    w.sidebar.toggle()
    w.sidebar.anim.setCurrentTime(w.sidebar.anim.duration())
    assert w.sidebar.maximumWidth() == w.sidebar.COLLAPSED
    assert w.sidebar.items[0][0].text() == "📋"
