"""First-launch onboarding: a welcome, three quick setup questions, and a
nudge to add deadlines. Shown once (State.onboarded); the Demo page can
replay it.

Pages: 0 welcome · 1 how you work · 2 what you play · 3 how hard to nudge ·
4 which AI estimates · 5 all set. The four dots track pages 1-4.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..llm import BACKENDS
from ..llm.claude_cli import AccountStatus, account_status, cached_status, forget_status, open_login_terminal
from ..models import NotifyLevel, Style, WorkingStyle
from .window import ICONS_DIR, ConfirmModal, GameList, Job, Modal, label, styled_combo

QUIZ_PAGES = 4  # pages 1-4 are questions, with a dot each
DONE = QUIZ_PAGES + 1

STYLES = [Style.SHORT_BURSTS, Style.MIXED, Style.LONG_SESSIONS]
STYLE_NAMES = ["Short bursts", "Mixed", "Long sessions"]
STYLE_HINTS = [
    "Lots of short blocks, about an hour each.",
    "A mix of short and longer blocks.",
    "Fewer, longer blocks of three hours or more.",
]
LEVELS = [NotifyLevel.OFF, NotifyLevel.NORMAL, NotifyLevel.INTERRUPT]
LEVEL_NAMES = ["Silent", "Standard", "Interrupting"]
LEVEL_HINTS = [
    "No reminders or break alerts. The menu bar icon and your deadline cards still show what's at risk.",
    "A notification when you open a game while behind on a deadline, and a break alert once you pass "
    "your session limit.",
    "Like Standard, but break alerts also bring Gameline to the front, even over a fullscreen game.",
]


class StepSlider(QWidget):
    """A three-stop slider with a name under each stop."""

    def __init__(self, names: list[str], value: int, on_change: Callable[[int], None]) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName("stepSlider")
        self.slider.setRange(0, len(names) - 1)
        self.slider.setPageStep(1)
        self.slider.setValue(value)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.valueChanged.connect(on_change)
        self.slider.valueChanged.connect(self._highlight)
        lay.addWidget(self.slider)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.names = []
        for i, name in enumerate(names):
            lbl = QLabel(name)
            lbl.setObjectName("stop")
            align = Qt.AlignmentFlag.AlignLeft if i == 0 else (
                Qt.AlignmentFlag.AlignRight if i == len(names) - 1 else Qt.AlignmentFlag.AlignHCenter)
            lbl.setAlignment(align)
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.mousePressEvent = lambda e, i=i: self.slider.setValue(i)
            row.addWidget(lbl, 1)
            self.names.append(lbl)
        lay.addLayout(row)
        self._highlight(value)

    def _highlight(self, value: int) -> None:
        for i, lbl in enumerate(self.names):
            lbl.setProperty("current", i == value)
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

    def value(self) -> int:
        return self.slider.value()


class Pages(QWidget):
    """Like QStackedWidget, but only the current page takes up space: hidden
    pages drop out of the layout, so the card fits each page snugly."""

    def __init__(self) -> None:
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self._pages: list[QWidget] = []
        self._index = 0

    def addWidget(self, page: QWidget) -> None:
        self._pages.append(page)
        self.lay.addWidget(page)
        page.setVisible(len(self._pages) == 1)

    def setCurrentIndex(self, index: int) -> None:
        self._index = index
        for i, page in enumerate(self._pages):
            page.setVisible(i == index)

    def currentIndex(self) -> int:
        return self._index

    def currentWidget(self) -> QWidget:
        return self._pages[self._index]


class OnboardingModal(Modal):
    def __init__(self, window, on_add_deadline: Callable[[], None], on_import: Callable[[], None]) -> None:
        super().__init__(window.centralWidget(), "", width=520)
        self.window_ = window
        self.ctx = window.ctx
        self.on_add_deadline, self.on_import = on_add_deadline, on_import
        self.heading.hide()  # each page has its own header
        ws = self.ctx.store.load().working_style
        self.style_idx = STYLES.index(Style(ws.style)) if Style(ws.style) in STYLES else 1
        self.level_idx = LEVELS.index(NotifyLevel(ws.notify_level))
        self.interrupt_ok = False

        self.pages = Pages()
        for build in (self._welcome, self._work, self._play, self._nudge, self._ai, self._done):
            self.pages.addWidget(build())
        self.body.addWidget(self.pages)

        # Footer: Back · dots · Next
        foot = QHBoxLayout()
        self.back_btn = QPushButton("Back")
        self.back_btn.setProperty("ghost", True)
        self.back_btn.clicked.connect(lambda: self.go(self.pages.currentIndex() - 1))
        foot.addWidget(self.back_btn)
        foot.addStretch(1)
        self.dots = []
        for _ in range(QUIZ_PAGES):
            dot = QLabel()
            dot.setObjectName("dot")
            dot.setFixedSize(8, 8)
            foot.addWidget(dot)
            self.dots.append(dot)
        foot.addStretch(1)
        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.next)
        foot.addWidget(self.next_btn)
        self.footer = QWidget()
        self.footer.setLayout(foot)
        self.body.addWidget(self.footer)
        self.go(0)
        self.open(focus=self.start_btn)

    # Onboarding isn't dismissed by a stray click or Esc; use Skip instead.
    def mousePressEvent(self, event) -> None:
        pass

    def keyPressEvent(self, event) -> None:
        if event.key() != Qt.Key.Key_Escape:
            super().keyPressEvent(event)

    def close_modal(self) -> None:
        if self.pages.currentIndex() in (0, DONE) or getattr(self, "_finishing", False):
            super().close_modal()

    # --- pages -------------------------------------------------------------

    @staticmethod
    def _page(title: str, subtitle: str = "") -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 4, 0, 8)
        lay.setSpacing(12)
        lay.addWidget(label(title, name="modalTitle"))
        if subtitle:
            lay.addWidget(label(subtitle, muted=True, wrap=True))
        return page, lay

    def _welcome(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 16, 0, 8)
        lay.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(QIcon(str(ICONS_DIR / "logo.svg")).pixmap(88, 88))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(logo)
        title = label("Welcome to Gameline!", name="welcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        sub = label("Manage your deadlines and game responsibly!", muted=True)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(sub)
        lay.addSpacing(10)
        self.start_btn = QPushButton("Get started")
        self.start_btn.clicked.connect(lambda: self.go(1))
        lay.addWidget(self.start_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        skip = QPushButton("Skip setup")
        skip.setObjectName("linkButton")
        skip.clicked.connect(self.skip)
        lay.addWidget(skip, 0, Qt.AlignmentFlag.AlignHCenter)
        return page

    def _work(self) -> QWidget:
        page, lay = self._page("How do you like to work?", "This shapes how Gameline splits deadlines into work blocks.")
        self.style_hint = label(STYLE_HINTS[self.style_idx], muted=True, wrap=True)
        self.style_slider = StepSlider(STYLE_NAMES, self.style_idx, self._style_changed)
        lay.addWidget(self.style_slider)
        lay.addWidget(self.style_hint)
        lay.addSpacing(6)
        row = QHBoxLayout()
        row.addWidget(QLabel("Work hours per day"), 1)
        self.hours = QDoubleSpinBox()
        self.hours.setRange(0.5, 16)
        self.hours.setSingleStep(0.5)
        self.hours.setDecimals(2)
        self.hours.setSuffix(" h")
        self.hours.setValue(self.ctx.store.load().working_style.daily_work_hours or 4.0)
        self.hours.setFixedSize(140, 36)
        self.hours.lineEdit().setTextMargins(10, 0, 10, 0)
        row.addWidget(self.hours)
        lay.addLayout(row)
        return page

    def _play(self) -> QWidget:
        page, lay = self._page("What and how do you play?")
        row = QHBoxLayout()
        row.addWidget(QLabel("Gaming session limit"), 1)
        self.limit = QSpinBox()
        self.limit.setRange(15, 600)
        self.limit.setSingleStep(15)
        self.limit.setSuffix(" min")
        self.limit.setValue(self.ctx.store.load().working_style.max_gaming_minutes)
        self.limit.setFixedSize(140, 36)
        self.limit.lineEdit().setTextMargins(10, 0, 10, 0)
        row.addWidget(self.limit)
        lay.addLayout(row)
        lay.addWidget(label("You'll get a break alert after playing this long in one go.", muted=True, wrap=True))
        lay.addSpacing(6)
        lay.addWidget(QLabel("Play anything that isn't on Steam or Epic?"))
        lay.addWidget(label("Steam and Epic games are found automatically. Add anything else you play, "
                            "like Minecraft or League of Legends.", muted=True, wrap=True))
        self.games = GameList(self._add_game, self._remove_game, collapsible=False)
        self.games.setFixedWidth(472)
        self.games.set_games(self.ctx.store.load().tagged_games)
        lay.addWidget(self.games)
        return page

    def _nudge(self) -> QWidget:
        page, lay = self._page("How hard should we nudge?")
        self.level_slider = StepSlider(LEVEL_NAMES, self.level_idx, self._level_changed)
        lay.addWidget(self.level_slider)
        self.level_hint = label("", wrap=True)
        lay.addWidget(self.level_hint)
        self.level_warn = label("Caution: this can interrupt online games or intense moments.",
                                name="warning", wrap=True)
        lay.addWidget(self.level_warn)
        self._level_changed(self.level_idx)
        return page

    def _ai(self) -> QWidget:
        page, lay = self._page("Who should plan your deadlines?",
                               "Gameline asks an AI to estimate each deadline and split it into work blocks.")
        self.ai_box = styled_combo()
        for key, text in BACKENDS.items():
            self.ai_box.addItem(text, key)
        self.ai_box.setFixedHeight(36)
        self.ai_box.setCurrentIndex(max(0, self.ai_box.findData(self.ctx.backend_name())))
        self.ai_box.currentIndexChanged.connect(self._ai_changed)
        lay.addWidget(self.ai_box)
        self.ai_hint = label("", muted=True, wrap=True)
        lay.addWidget(self.ai_hint)

        # Claude subscription only: log in right here, like in Preferences.
        self.login_row = QWidget()
        lr = QHBoxLayout(self.login_row)
        lr.setContentsMargins(0, 4, 0, 0)
        lr.setSpacing(12)
        self.login_btn = QPushButton("Log in with Claude")
        self.login_btn.setObjectName("claudeAccount")
        self.login_btn.setFixedHeight(36)
        self.login_btn.clicked.connect(self._login)
        lr.addWidget(self.login_btn)
        self.login_status = label("", muted=True, wrap=True)
        lr.addWidget(self.login_status, 1)
        lay.addWidget(self.login_row)

        self.claude: AccountStatus | None = None
        self.skip_login_ok = False
        self._checking = False
        self.login_timer = QTimer(self)
        self.login_timer.setInterval(6000)
        self.login_timer.timeout.connect(lambda: self._check_claude(force=True))
        self._ai_changed()
        return page

    def _ai_changed(self) -> None:
        key = self.ai_box.currentData()
        self.ai_hint.setText({
            "gemini": "Uses the Gemini API key from your .env file.",
            "claude": "Uses the Claude API key from your .env file.",
            "claude-cli": "Uses your Claude subscription through Claude Code on this Mac. Just log in below.",
            "stub": "No AI: rough guesses from the deadline's title. Works offline.",
        }.get(key, ""))
        self.login_row.setVisible(key == "claude-cli")
        self.skip_login_ok = False
        if key == "claude-cli" and hasattr(self, "pages") and self.pages.currentIndex() == QUIZ_PAGES:
            self._check_claude()
        if hasattr(self, "footer"):
            self._fit()

    def _check_claude(self, force: bool = False) -> None:
        if not force:
            cached = cached_status()
            if cached is not None:
                self._show_login(cached)
                return
        if self._checking:
            return
        self._checking = True
        if not self.login_timer.isActive():
            self.login_btn.setText("Checking Claude…")
            self.login_btn.setEnabled(False)
        self.window_.pool.start(Job(account_status, self._claude_checked))

    def _claude_checked(self, status) -> None:
        self._checking = False
        if isinstance(status, AccountStatus):
            self._show_login(status)
            if status.ok:
                self.login_timer.stop()

    def _show_login(self, status: AccountStatus) -> None:
        self.claude = status
        ok = status.ok
        if not status.installed:
            text, tone, enabled, note = "Claude Code not installed", "idle", False, \
                "Install Claude Code, or pick another option."
        elif ok:
            text, tone, enabled = "✓  Logged in to Claude", "ok", False
            note = status.email + (f" · {status.plan.title()}" if status.plan else "")
        elif self.login_timer.isActive():
            text, tone, enabled, note = "Waiting for login…", "idle", False, "Finish logging in in your browser."
        else:
            text, tone, enabled, note = "Log in with Claude", "action", True, "Not logged in yet."
        self.login_btn.setText(text)
        self.login_btn.setEnabled(enabled)
        self.login_btn.setProperty("tone", tone)
        self.login_btn.style().unpolish(self.login_btn)
        self.login_btn.style().polish(self.login_btn)
        self.login_status.setText(note)

    def _login(self) -> None:
        forget_status()
        open_login_terminal()
        self.login_timer.start()
        self._show_login(AccountStatus(installed=True))

    def _done(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 12, 0, 8)
        lay.setSpacing(10)
        tick = QLabel("✓")
        tick.setObjectName("bigTick")
        tick.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(tick)
        title = label("You're all set!", name="welcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        sub = label("Add your first deadlines: Gameline will plan the work while keeping an eye on your game time.",
                    muted=True, wrap=True)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(sub)
        lay.addSpacing(8)
        row = QHBoxLayout()
        row.addStretch(1)
        add = QPushButton("Add a deadline")
        add.clicked.connect(lambda: self.finish(self.on_add_deadline))
        imp = QPushButton("Import a syllabus")
        imp.setObjectName("secondary")
        imp.clicked.connect(lambda: self.finish(self.on_import))
        row.addWidget(add)
        row.addWidget(imp)
        row.addStretch(1)
        lay.addLayout(row)
        later = QPushButton("I'll do it later")
        later.setObjectName("linkButton")
        later.clicked.connect(lambda: self.finish(None))
        lay.addWidget(later, 0, Qt.AlignmentFlag.AlignHCenter)
        return page

    # --- behaviour ---------------------------------------------------------

    def _style_changed(self, i: int) -> None:
        self.style_idx = i
        self.style_hint.setText(STYLE_HINTS[i])

    def _level_changed(self, i: int) -> None:
        self.level_idx = i
        self.interrupt_ok = False  # changing back and forth asks again
        self.level_hint.setText(LEVEL_HINTS[i])
        self.level_warn.setVisible(LEVELS[i] == NotifyLevel.INTERRUPT)
        if hasattr(self, "footer"):
            self._fit()

    def _add_game(self, name: str) -> bool:
        if not name.strip() or not self.ctx.add_tagged_game(name):
            return False
        self.games.set_games(self.ctx.store.load().tagged_games)
        return True

    def _remove_game(self, name: str) -> None:
        self.ctx.remove_tagged_game(name)
        self.games.set_games(self.ctx.store.load().tagged_games)

    def _fit(self) -> None:
        """Size the card to the current page only (a stack is as tall as its
        tallest page otherwise), then re-centre it."""
        self.pages.lay.activate()
        self.pages.adjustSize()
        self.body.activate()
        self.card.adjustSize()
        self._center_card()

    def go(self, index: int) -> None:
        index = max(0, min(DONE, index))
        self.pages.setCurrentIndex(index)
        quiz = 1 <= index <= QUIZ_PAGES
        self.footer.setVisible(quiz)
        for i, dot in enumerate(self.dots):
            dot.setProperty("current", i == index - 1)
            dot.style().unpolish(dot)
            dot.style().polish(dot)
        self.back_btn.setVisible(quiz)
        self.next_btn.setText("Finish" if index == QUIZ_PAGES else "Next")
        if index == QUIZ_PAGES and self.ai_box.currentData() == "claude-cli":
            self._check_claude()  # only look at the login once this page is on screen
        self._fit()

    def next(self) -> None:
        index = self.pages.currentIndex()
        if index == 3:
            if LEVELS[self.level_idx] == NotifyLevel.INTERRUPT and not self.interrupt_ok:
                ConfirmModal(
                    self.parent(),
                    "Use interrupting notifications?",
                    "When a gaming session runs past your limit, Gameline will bring its window to the front, "
                    "even over a fullscreen game.",
                    "This can interrupt online games or intense moments.",
                    "I understand",
                    self._accept_interrupt,
                )
                return
        if index == QUIZ_PAGES:
            if self.ai_box.currentData() == "claude-cli" and not (self.claude and self.claude.ok) \
                    and not self.skip_login_ok:
                ConfirmModal(
                    self.parent(),
                    "Continue without logging in?",
                    "Claude subscription estimates only work once Claude Code on this Mac is logged in. "
                    "Until then, new deadlines won't get estimates. You can log in later in Preferences.",
                    "Estimates will fail until you log in.",
                    "Continue anyway",
                    self._accept_no_login,
                )
                return
            self._save()
        self.go(index + 1)

    def _accept_no_login(self) -> None:
        self.skip_login_ok = True
        self.raise_()
        self.next()

    def _accept_interrupt(self) -> None:
        self.interrupt_ok = True
        self.raise_()
        self.next()

    def _save(self) -> None:
        self.ctx.set_backend(self.ai_box.currentData())
        self.ctx.finish_onboarding(WorkingStyle(
            style=STYLES[self.style_idx],
            daily_work_hours=self.hours.value(),
            max_gaming_minutes=self.limit.value(),
            notify_level=LEVELS[self.level_idx],
        ))

    def skip(self) -> None:
        self.ctx.finish_onboarding(None)
        self.finish(None)

    def finish(self, then: Callable[[], None] | None) -> None:
        self._finishing = True
        self.close_modal()
        self.window_.after_onboarding()
        if then:
            then()
