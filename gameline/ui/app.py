"""Application entry: Qt event loop, menu bar (tray) icon, watcher thread.

Qt owns the main thread. The watcher polls on its own thread and only talks
to the UI through the shared store, which the window re-reads on a timer.
"""

from __future__ import annotations

import sys
import threading

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from ..context import AppContext
from ..notify import notify
from ..reminders import Reminders
from ..watcher import Watcher
from .theme import palette, stylesheet
from .window import ICONS_DIR, MainWindow


def make_icon(at_risk: bool) -> QIcon:
    """App logo with a red alert badge when a deadline is at risk, a green check otherwise."""
    return QIcon(str(ICONS_DIR / ("logo-risk.svg" if at_risk else "logo-ok.svg")))


class InterruptBridge(QObject):
    """Carries interrupting alerts from the watcher thread to the GUI thread.
    Emitting a Qt signal across threads queues the call onto the receiver's thread."""

    fired = Signal(str, str)


class GamelineApp:
    def __init__(self, qapp: QApplication) -> None:
        self.qapp = qapp
        self.ctx = AppContext()
        self.bridge = InterruptBridge()
        reminders = Reminders(self.ctx.store, self.ctx.clock, interrupt=self.bridge.fired.emit)
        self.watcher = Watcher(self.ctx.detectors, reminders, clock=self.ctx.clock, interval=3)
        self.window = MainWindow(self.ctx, self.playing)
        self.bridge.fired.connect(self.window.interrupt)
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
        menu.addAction("Send test notification", self.test_notification)
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

    def test_notification(self) -> None:
        # Off the GUI thread: notify() blocks briefly while macOS delivers it.
        threading.Thread(target=notify, args=("Gameline test", "Notifications are working."), daemon=True).start()

    def quit(self) -> None:
        self.watcher.stop()
        self.ctx.stop_fake_game()
        self.tray.hide()
        self.qapp.quit()


def run() -> None:
    qapp = QApplication(sys.argv)
    qapp.setApplicationName("Gameline")
    qapp.setWindowIcon(QIcon(str(ICONS_DIR / "logo.svg")))  # Dock and app switcher
    qapp.setQuitOnLastWindowClosed(False)  # live on in the menu bar
    # Fusion renders stylesheets the same on every OS, unlike the native Mac style.
    qapp.setStyle("Fusion")
    qapp.setPalette(palette())
    qapp.setStyleSheet(stylesheet())
    app = GamelineApp(qapp)  # noqa: F841 (must stay alive for the event loop)
    sys.exit(qapp.exec())
