import os
from datetime import datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from gameline.context import AppContext  # noqa: E402
from gameline.store import Store  # noqa: E402
from gameline.ui.window import DeadlineDialog, MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_dialog_round_trips_datetime(qapp):
    win = QtWidgets.QWidget()
    due = datetime(2026, 10, 20, 23, 59)
    dlg = DeadlineDialog(win, datetime(2026, 10, 17, 12, 0))
    dlg.title.setText("A2")
    dlg.due.setDateTime(dlg.due.dateTime().fromString("2026-10-20T23:59", "yyyy-MM-ddTHH:mm"))
    assert dlg.values()[1] == due


def test_window_renders_seeded_week(qapp, tmp_path):
    ctx = AppContext(Store(tmp_path / "s.json"))
    ctx.seed_demo_data()
    w = MainWindow(ctx, lambda: [])
    assert w.cards.count() == 3  # two cards + stretch
    assert w.status_pill.text() == "1 deadline at risk"
