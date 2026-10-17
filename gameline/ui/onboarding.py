"""First-launch onboarding: a welcome, three quick setup questions, and a
nudge to add deadlines. Shown once (State.onboarded); the Demo page can
replay it.

Pages: 0 welcome · 1 how you work · 2 what you play · 3 how hard to nudge ·
4 all set. The three dots track pages 1-3.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
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

from ..models import NotifyLevel, Style, WorkingStyle
from .window import ICONS_DIR, ConfirmModal, GameList, Modal, label

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
        for build in (self._welcome, self._work, self._play, self._nudge, self._done):
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
        for _ in range(3):
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
        if self.pages.currentIndex() in (0, 4) or getattr(self, "_finishing", False):
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
        self.games = GameList(self._add_game, self._remove_game)
        self.games.setFixedWidth(472)
        self.games.on_resize = lambda: self._fit()
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
        sub = label("Add your first deadlines and Gameline will plan the work and keep an eye on your game time.",
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
        self._fit()
        return True

    def _remove_game(self, name: str) -> None:
        self.ctx.remove_tagged_game(name)
        self.games.set_games(self.ctx.store.load().tagged_games)
        self._fit()

    def _fit(self) -> None:
        """Size the card to the current page only (a stack is as tall as its
        tallest page otherwise), then re-centre it."""
        self.pages.lay.activate()
        self.pages.adjustSize()
        self.body.activate()
        self.card.adjustSize()
        self._center_card()

    def go(self, index: int) -> None:
        index = max(0, min(4, index))
        self.pages.setCurrentIndex(index)
        quiz = 1 <= index <= 3
        self.footer.setVisible(quiz)
        for i, dot in enumerate(self.dots):
            dot.setProperty("current", i == index - 1)
            dot.style().unpolish(dot)
            dot.style().polish(dot)
        self.back_btn.setVisible(quiz)
        self.next_btn.setText("Finish" if index == 3 else "Next")
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
            self._save()
        self.go(index + 1)

    def _accept_interrupt(self) -> None:
        self.interrupt_ok = True
        self.raise_()
        self.next()

    def _save(self) -> None:
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
