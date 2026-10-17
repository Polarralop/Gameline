"""Application entry: Qt event loop, menu bar (tray) icon, watcher thread.

Qt owns the main thread. The watcher polls on its own thread and only talks
to the UI through the shared store, which the window re-reads on a timer.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from ..context import AppContext
from ..reminders import Reminders
from ..watcher import Watcher
from .theme import stylesheet
from .window import MainWindow


def make_icon(at_risk: bool) -> QIcon:
    """Controller emoji, with an orange dot when a deadline is at risk."""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    font = QFont()
    font.setPixelSize(50)
    p.setFont(font)
    p.drawText(QRect(0, 0, 64, 64), Qt.AlignmentFlag.AlignCenter, "🎮")
    if at_risk:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#f97316"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(40, 2, 22, 22)
    p.end()
    return QIcon(pm)


class GamelineApp:
    def __init__(self, qapp: QApplication) -> None:
        self.qapp = qapp
        self.ctx = AppContext()
        self.watcher = Watcher(self.ctx.detectors, Reminders(self.ctx.store, self.ctx.clock), clock=self.ctx.clock, interval=3)
        self.window = MainWindow(self.ctx, self.playing)
        self.icons = {False: make_icon(False), True: make_icon(True)}

        self.tray = QSystemTrayIcon(self.icons[False])
        menu = QMenu()
        self.status_action = QAction("Starting…")
        self.status_action.setEnabled(False)
        menu.addAction(self.status_action)
        menu.addSeparator()
        menu.addAction("Open Gameline", self.show_window)
        menu.addSeparator()
        self.demo_action = QAction("Demo speed (6 min/s)", checkable=True)
        self.demo_action.toggled.connect(self.ctx.set_demo_mode)
        menu.addAction(self.demo_action)
        self.game_action = menu.addAction("Launch fake game", self.toggle_fake_game)
        menu.addSeparator()
        menu.addAction("Quit Gameline", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("Gameline")
        self.menu = menu  # keep a reference so Python doesn't garbage-collect it
        self.tray.show()

        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        self.refresh()

        self.watcher.start()
        self.show_window()

    def playing(self) -> list[str]:
        return [s.game.name for s in list(self.watcher.sessions.values())]

    def refresh(self) -> None:
        status = self.ctx.status_line()
        playing = self.playing()
        self.tray.setIcon(self.icons[status != "On track"])
        self.status_action.setText(status + (f" · playing {', '.join(playing)}" if playing else ""))
        self.demo_action.blockSignals(True)
        self.demo_action.setChecked(self.ctx.demo_mode)
        self.demo_action.blockSignals(False)
        self.game_action.setText("Quit fake game" if self.ctx.fake_game_running else "Launch fake game")

    def show_window(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def toggle_fake_game(self) -> None:
        if self.ctx.fake_game_running:
            self.ctx.stop_fake_game()
        else:
            self.ctx.start_fake_game()
        self.refresh()

    def quit(self) -> None:
        self.watcher.stop()
        self.ctx.stop_fake_game()
        self.tray.hide()
        self.qapp.quit()


def run() -> None:
    qapp = QApplication(sys.argv)
    qapp.setApplicationName("Gameline")
    qapp.setQuitOnLastWindowClosed(False)  # live on in the menu bar
    qapp.setStyleSheet(stylesheet())
    app = GamelineApp(qapp)  # noqa: F841 (must stay alive for the event loop)
    sys.exit(qapp.exec())
