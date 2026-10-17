"""Menu bar app (rumps).

rumps pattern in brief: subclass rumps.App, decorate methods with
@rumps.clicked("Menu item") to handle clicks, and use rumps.Timer for
periodic UI updates. rumps must own the main thread, so the watcher and the
Flask dashboard each run on their own background thread.
"""

from __future__ import annotations

import logging
import threading
import webbrowser

import rumps
from werkzeug.serving import make_server

from .context import AppContext
from .dashboard import HOST, PORT, URL, create_app
from .reminders import Reminders
from .watcher import Watcher

log = logging.getLogger(__name__)

ICON_OK, ICON_RISK = "🎮", "🎮⚠️"


class GamelineApp(rumps.App):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__("Gameline", title=ICON_OK, quit_button=None)
        self.ctx = ctx
        self.status_item = rumps.MenuItem("Starting…")
        self.demo_item = rumps.MenuItem("Demo speed (6 min/s)", callback=self.toggle_demo)
        self.fake_item = rumps.MenuItem("Launch fake game", callback=self.toggle_fake_game)
        self.menu = [
            self.status_item,
            None,
            rumps.MenuItem("Open dashboard", callback=self.open_dashboard),
            None,
            self.demo_item,
            self.fake_item,
            None,
            rumps.MenuItem("Quit Gameline", callback=self.quit),
        ]

        self.watcher = Watcher(ctx.detectors, Reminders(ctx.store, ctx.clock), clock=ctx.clock, interval=3)
        self.server = make_server(HOST, PORT, create_app(ctx), threaded=True)
        threading.Thread(target=self.server.serve_forever, name="gameline-dashboard", daemon=True).start()
        self.watcher.start()
        rumps.Timer(self.refresh, 2).start()

    def refresh(self, _timer=None) -> None:
        status = self.ctx.status_line()
        playing = [s.game.name for s in self.watcher.sessions.values()]
        self.title = ICON_OK if status == "On track" else ICON_RISK
        self.status_item.title = status + (f" · playing {', '.join(playing)}" if playing else "")
        self.demo_item.state = self.ctx.demo_mode
        self.fake_item.title = "Quit fake game" if self.ctx.fake_game_running else "Launch fake game"

    def open_dashboard(self, _=None) -> None:
        webbrowser.open(URL)

    def toggle_demo(self, _=None) -> None:
        self.ctx.set_demo_mode(not self.ctx.demo_mode)
        self.refresh()

    def toggle_fake_game(self, _=None) -> None:
        if self.ctx.fake_game_running:
            self.ctx.stop_fake_game()
        else:
            self.ctx.start_fake_game()
        self.refresh()

    def quit(self, _=None) -> None:
        self.watcher.stop()
        self.ctx.stop_fake_game()
        self.server.shutdown()
        rumps.quit_application()


def run() -> None:
    GamelineApp(AppContext()).run()
