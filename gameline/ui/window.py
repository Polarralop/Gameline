"""The main Gameline window: deadlines, settings and demo controls.

Qt patterns used here:
- Layouts (QVBoxLayout/QHBoxLayout/QFormLayout) position child widgets.
- Signals and slots: button.clicked.connect(fn) calls fn on click.
- Slow work (LLM estimates) runs on QThreadPool; a Signal carries the result
  back, because widgets may only be touched from the main (GUI) thread.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import (
    QDateTime,
    QEvent,
    QEasingCurve,
    QObject,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..context import AppContext
from ..models import Deadline, Style, WorkingStyle
from ..planner import DeadlineStatus, assess

STYLE_LABELS = {Style.SHORT_BURSTS: "Short bursts", Style.MIXED: "Mixed", Style.LONG_SESSIONS: "Long sessions"}


def label(text: str = "", *, name: str | None = None, muted: bool = False, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    if muted:
        lbl.setProperty("muted", True)
    lbl.setWordWrap(wrap)
    return lbl


def pill(text: str, tone: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("pill", tone)
    return lbl


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%a %b %-d, %-I:%M %p")


def to_qdt(dt: datetime) -> QDateTime:
    return QDateTime(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0)


def from_qdt(q: QDateTime) -> datetime:
    return q.toPython().replace(second=0, microsecond=0)


# --- background jobs ---------------------------------------------------------


class _JobSignals(QObject):
    done = Signal(object)


class Job(QRunnable):
    """Run fn() on the thread pool and emit its result on the GUI thread."""

    def __init__(self, fn: Callable[[], object], on_done: Callable[[object], None]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _JobSignals()
        self.signals.done.connect(on_done)

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:  # surface errors in the UI instead of dying silently
            result = [f"{exc.__class__.__name__}: {exc}"]
        self.signals.done.emit(result)


# --- in-window modals --------------------------------------------------------


class Modal(QWidget):
    """Base in-window modal: dims the window and shows a card in the middle.

    It is a child widget laid over the host, not a separate window. Subclasses
    fill self.body (the card's layout) and then call self.open(). Esc or a
    click on the dimmed area cancels.
    """

    def __init__(self, host: QWidget, heading: str, width: int = 480) -> None:
        super().__init__(host)
        self.setGeometry(host.rect())
        host.installEventFilter(self)  # follow the window when it resizes
        self.card = QFrame(self)
        self.card.setObjectName("modal")
        self.card.setFixedWidth(width)
        self.body = QVBoxLayout(self.card)
        self.body.setContentsMargins(22, 20, 22, 18)
        self.body.setSpacing(10)
        self.body.addWidget(label(heading, name="modalTitle"))
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.close_modal)

    def add_buttons(self, confirm_text: str, on_confirm: Callable[[], None], danger: bool = False) -> QPushButton:
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setProperty("ghost", True)
        cancel.clicked.connect(self.close_modal)
        confirm = QPushButton(confirm_text)
        confirm.setDefault(True)
        if danger:
            confirm.setProperty("danger", True)
        confirm.clicked.connect(on_confirm)
        row.addWidget(cancel)
        row.addWidget(confirm)
        self.body.addSpacing(4)
        self.body.addLayout(row)
        return confirm

    def open(self, focus: QWidget | None = None) -> None:
        self._center_card()
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.fade = QPropertyAnimation(self.effect, b"opacity", self)
        self.fade.setDuration(140)
        self.fade.setStartValue(0.0)
        self.fade.setEndValue(1.0)
        self.show()
        self.raise_()
        self.fade.start()
        (focus or self).setFocus()

    def _center_card(self) -> None:
        self.card.adjustSize()
        self.card.move((self.width() - self.card.width()) // 2, max(40, (self.height() - self.card.height()) // 2 - 30))

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Resize:
            self.setGeometry(obj.rect())
            self._center_card()
        return False

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))

    def mousePressEvent(self, event) -> None:
        if not self.card.geometry().contains(event.position().toPoint()):
            self.close_modal()

    def close_modal(self) -> None:
        self.parent().removeEventFilter(self)
        self.deleteLater()


class DeadlineModal(Modal):
    """Add or edit a deadline. on_save(title, due, notes) runs on Save."""

    def __init__(
        self,
        host: QWidget,
        now: datetime,
        on_save: Callable[[str, datetime, str], None],
        deadline: Deadline | None = None,
    ) -> None:
        super().__init__(host, "Edit deadline" if deadline else "Add deadline")
        self.on_save = on_save

        self.title = QLineEdit(deadline.title if deadline else "")
        self.title.setPlaceholderText("CSCA48 Assignment 2")
        self.title.returnPressed.connect(self._save)
        self.due = QDateTimeEdit(to_qdt(deadline.due if deadline else now.replace(hour=23, minute=59)))
        self.due.setCalendarPopup(True)
        self.due.setDisplayFormat("ddd MMM d, h:mm AP")
        self.notes = QPlainTextEdit(deadline.notes if deadline else "")
        self.notes.setPlaceholderText("Details help the estimate, e.g. 4 coding questions on linked lists")
        self.notes.setFixedHeight(80)

        form = QFormLayout()
        form.addRow("Title", self.title)
        form.addRow("Due", self.due)
        form.addRow("Details", self.notes)
        self.body.addLayout(form)
        self.body.addWidget(label("Gameline will ask the AI to estimate effort and plan work blocks.", muted=True, wrap=True))
        self.add_buttons("Save", self._save)
        self.open(focus=self.title)

    def values(self) -> tuple[str, datetime, str]:
        return self.title.text(), from_qdt(self.due.dateTime()), self.notes.toPlainText()

    def _save(self) -> None:
        if not self.title.text().strip():
            self.title.setFocus()
            return
        values = self.values()
        self.close_modal()
        self.on_save(*values)


class ConfirmModal(Modal):
    """Yes/no question with a short warning line, e.g. before deleting."""

    def __init__(
        self,
        host: QWidget,
        heading: str,
        message: str,
        warning: str,
        confirm_text: str,
        on_confirm: Callable[[], None],
    ) -> None:
        super().__init__(host, heading, width=400)
        self.on_confirm = on_confirm
        self.body.addWidget(label(message, wrap=True))
        warn = label(warning, name="warning", wrap=True)
        self.body.addWidget(warn)
        self.confirm_btn = self.add_buttons(confirm_text, self._confirm, danger=True)
        self.open(focus=self.confirm_btn)

    def _confirm(self) -> None:
        self.close_modal()
        self.on_confirm()


# --- deadline card -----------------------------------------------------------


class DeadlineCard(QFrame):
    def __init__(self, window: MainWindow, s: DeadlineStatus) -> None:
        super().__init__()
        self.setObjectName("card")
        d = s.deadline
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)

        top = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(2)
        left.addWidget(label(d.title, name="title"))
        meta = f"Due {fmt_dt(d.due)}"
        if d.estimate:
            meta += f" · importance {d.estimate.importance}/5"
        left.addWidget(label(meta, muted=True))
        top.addLayout(left, 1)
        if not d.estimate:
            top.addWidget(pill("Estimating…" if window.busy else "Not estimated", "ok"), 0, Qt.AlignmentFlag.AlignTop)
        else:
            top.addWidget(pill("At risk" if s.at_risk else "On track", "risk" if s.at_risk else "ok"), 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(top)

        if d.estimate:
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setRange(0, 100)
            have = s.available_hours
            bar.setValue(100 if have <= 0 else min(100, round(s.remaining_hours / have * 100)))
            bar.setProperty("tone", "risk" if s.at_risk else "ok")
            lay.addWidget(bar)
            lay.addWidget(label(
                f"{s.remaining_hours:.1f}h of work left · {have:.1f}h realistically available · "
                f"slack {s.slack_hours:+.1f}h", muted=True))
            if d.estimate.rationale:
                lay.addWidget(label(d.estimate.rationale, muted=True, wrap=True))
            for i, c in enumerate(d.estimate.chunks):
                text = f"{c.title} · {c.hours:g}h"
                if c.start:
                    text += f" · {c.start.strftime('%a %-I:%M %p')}"
                box = QCheckBox(text)
                box.setChecked(c.done)
                box.setProperty("done", c.done)
                box.toggled.connect(lambda on, i=i, did=d.id: window.toggle_chunk(did, i, on))
                lay.addWidget(box)

        actions = QHBoxLayout()
        actions.addStretch(1)
        for text, fn in (("Edit", lambda: window.edit_deadline(d)), ("Delete", lambda: window.delete_deadline(d))):
            b = QPushButton(text)
            b.setProperty("ghost", True)
            b.clicked.connect(fn)
            actions.addWidget(b)
        lay.addLayout(actions)


# --- sidebar -----------------------------------------------------------------


class Sidebar(QFrame):
    """Navigation rail that collapses to icons only. Width changes are animated."""

    EXPANDED, COLLAPSED = 210, 64

    def __init__(self, on_select: Callable[[int, str], None]) -> None:
        super().__init__()
        self.setObjectName("sidebar")
        self.on_select = on_select
        self.expanded = True
        self.items: list[tuple[QPushButton, str, str]] = []
        self.setFixedWidth(self.EXPANDED)

        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(10, 14, 10, 14)
        self.lay.setSpacing(4)

        # The top row is positioned by hand, not by a layout: a layout squeezes
        # its children when the animating sidebar gets narrow, which pushed the
        # brand into the toggle. Here both stay put and the sidebar edge clips.
        top = QWidget()
        top.setFixedSize(self.EXPANDED - 20, 34)
        self.toggle_btn = QPushButton("☰", top)
        self.toggle_btn.setObjectName("navToggle")
        self.toggle_btn.setToolTip("Collapse sidebar")
        self.toggle_btn.clicked.connect(self.toggle)
        self.toggle_btn.setGeometry(0, 0, self.COLLAPSED - 20, 34)
        self.brand = label("Gameline", name="brand")
        self.brand.setParent(top)
        self.brand.setGeometry(self.COLLAPSED - 12, 0, self.EXPANDED - self.COLLAPSED, 34)
        # Fade the brand in step with the width instead of popping it in/out.
        self.brand_fx = QGraphicsOpacityEffect(self.brand)
        self.brand_fx.setOpacity(1.0)  # Qt's default is 0.7
        self.brand.setGraphicsEffect(self.brand_fx)
        self.lay.addWidget(top, 0, Qt.AlignmentFlag.AlignLeft)
        self.lay.addSpacing(14)
        self.items_end = self.lay.count()
        self._top_count = 0
        self.lay.addStretch(1)

        self.anim = QParallelAnimationGroup(self)
        for prop in (b"minimumWidth", b"maximumWidth"):
            a = QPropertyAnimation(self, prop)
            a.setDuration(160)
            a.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim.addAnimation(a)
        self.anim.finished.connect(lambda: None if self.expanded else self._apply_labels())
        self.anim.animationAt(0).valueChanged.connect(self._fade_brand)

    def add_item(self, icon: str, text: str, bottom: bool = False) -> None:
        """Add a nav button. bottom=True pins it below the stretch, at the foot of the bar."""
        btn = QPushButton()
        btn.setObjectName("navItem")
        btn.setCheckable(True)
        btn.setToolTip(text)
        index = len(self.items)
        btn.clicked.connect(lambda: self.select(index))
        self.items.append((btn, icon, text))
        if bottom:
            self.lay.addWidget(btn)
        else:
            self.lay.insertWidget(self.items_end + self._top_count, btn)
            self._top_count += 1
        self._apply_labels()

    def select(self, index: int) -> None:
        for i, (btn, _, _) in enumerate(self.items):
            btn.setChecked(i == index)
        self.on_select(index, self.items[index][2])

    def toggle(self) -> None:
        self.expanded = not self.expanded
        start, end = (self.COLLAPSED, self.EXPANDED) if self.expanded else (self.EXPANDED, self.COLLAPSED)
        if self.expanded:
            # Show labels up front; the growing sidebar reveals them left to right.
            # Icons keep the same left padding in both states, so they never move.
            self._apply_labels()
        for i in range(self.anim.animationCount()):
            a = self.anim.animationAt(i)
            a.setStartValue(start)
            a.setEndValue(end)
        self.anim.start()
        self.toggle_btn.setToolTip("Collapse sidebar" if self.expanded else "Expand sidebar")

    def _fade_brand(self, width: int) -> None:
        span = self.EXPANDED - self.COLLAPSED
        self.brand_fx.setOpacity(max(0.0, min(1.0, (width - self.COLLAPSED) / span)) ** 2)

    def _apply_labels(self) -> None:
        for btn, icon, text in self.items:
            btn.setText(f"{icon}   {text}" if self.expanded else icon)


# --- main window -------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext, sessions: Callable[[], list[str]]) -> None:
        super().__init__()
        self.ctx = ctx
        self.sessions = sessions  # names of games currently being played
        self.busy = False
        self._signature = None
        self.pool = QThreadPool.globalInstance()

        self.setWindowTitle("Gameline")
        self.resize(1152, 648)  # 16:9, wide enough for the sidebar plus content

        page = QWidget()
        page.setObjectName("page")
        outer = QHBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.stack = QStackedWidget()
        self.sidebar = Sidebar(self._go_to)
        for icon, text, widget, bottom in (
            ("📋", "Deadlines", self._deadlines_tab(), False),
            ("🎬", "Demo", self._demo_tab(), False),
            ("⚙️", "Preferences", self._settings_tab(), True),
        ):
            self.stack.addWidget(widget)
            self.sidebar.add_item(icon, text, bottom=bottom)
        outer.addWidget(self.sidebar)

        content = QWidget()
        content.setObjectName("page")
        root = QVBoxLayout(content)
        root.setContentsMargins(24, 18, 24, 12)
        header = QHBoxLayout()
        self.page_title = label("", name="h1")
        header.addWidget(self.page_title)
        header.addStretch(1)
        self.status_pill = pill("", "ok")
        header.addWidget(self.status_pill)
        root.addLayout(header)
        self.clock_label = label(muted=True)
        root.addWidget(self.clock_label)
        root.addWidget(self.stack, 1)
        outer.addWidget(content, 1)
        self.setCentralWidget(page)
        self.sidebar.select(0)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh(force=True)

    def _go_to(self, index: int, text: str) -> None:
        self.stack.setCurrentIndex(index)
        self.page_title.setText(text)

    # pages

    def _deadlines_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(0, 14, 0, 0)
        bar = QHBoxLayout()
        self.add_btn = QPushButton("Add deadline")
        self.add_btn.clicked.connect(self.add_deadline)
        bar.addWidget(self.add_btn)
        bar.addStretch(1)
        lay.addLayout(bar)

        self.cards_host = QWidget()
        self.cards_host.setObjectName("page")
        self.cards = QVBoxLayout(self.cards_host)
        self.cards.setContentsMargins(0, 0, 4, 0)
        self.cards.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.cards_host)
        lay.addWidget(scroll, 1)
        return tab

    def _settings_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(0, 16, 0, 0)
        self.style_box = QComboBox()
        for st, text in STYLE_LABELS.items():
            self.style_box.addItem(text, st)
        self.daily_hours = QDoubleSpinBox()
        self.daily_hours.setRange(0.5, 16)
        self.daily_hours.setSingleStep(0.5)
        self.daily_hours.setSuffix(" h")
        self.max_minutes = QSpinBox()
        self.max_minutes.setRange(15, 600)
        self.max_minutes.setSingleStep(15)
        self.max_minutes.setSuffix(" min")
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("Minecraft, League of Legends")
        save = QPushButton("Save settings")
        save.clicked.connect(self.save_settings)

        form.addRow("Working style", self.style_box)
        form.addRow("Work hours per day", self.daily_hours)
        form.addRow("Gaming session limit", self.max_minutes)
        form.addRow("Extra apps to treat as games", self.tags)
        form.addRow("", label("Steam and Epic games are detected automatically.", muted=True))
        form.addRow("", save)
        self._load_settings()
        return tab

    def _demo_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(0, 16, 0, 0)
        lay.addWidget(label(
            "Load a sample week, launch the stand-in game, then speed up time so a long-session "
            "alert fires in seconds.", muted=True, wrap=True))
        row = QHBoxLayout()
        seed = QPushButton("Load sample week")
        seed.clicked.connect(self.seed_demo)
        self.speed_btn = QPushButton()
        self.speed_btn.clicked.connect(lambda: (self.ctx.set_demo_mode(not self.ctx.demo_mode), self.refresh(force=True)))
        self.game_btn = QPushButton()
        self.game_btn.clicked.connect(self.toggle_fake_game)
        for b in (seed, self.speed_btn, self.game_btn):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        return tab

    # refresh

    def refresh(self, force: bool = False) -> None:
        now = self.ctx.clock.now()
        playing = self.sessions()
        status = self.ctx.status_line()
        self.status_pill.setText(status)
        self._set_tone(self.status_pill, "ok" if status == "On track" else "risk")
        clock_text = f"App time {fmt_dt(now)}"
        if self.ctx.demo_mode:
            clock_text += " · demo speed on"
        if playing:
            clock_text += f" · playing {', '.join(playing)}"
        self.clock_label.setText(clock_text)
        self.speed_btn.setText("Back to real time" if self.ctx.demo_mode else "Speed up time (6 min/s)")
        self.game_btn.setText("Quit fake game" if self.ctx.fake_game_running else "Launch fake game")
        self.add_btn.setEnabled(not self.busy)

        # Rebuild cards only when something visible changed.
        path = self.ctx.store.path
        mtime = path.stat().st_mtime if path.exists() else 0
        sig = (mtime, now.strftime("%Y%m%d%H%M"), self.busy)
        if force or sig != self._signature:
            self._signature = sig
            self._rebuild_cards(now)

    @staticmethod
    def _set_tone(widget: QWidget, tone: str) -> None:
        widget.setProperty("pill", tone)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _rebuild_cards(self, now: datetime) -> None:
        while self.cards.count():
            item = self.cards.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        state = self.ctx.store.load()
        deadlines = sorted(state.deadlines, key=lambda d: d.due)
        if not deadlines:
            self.cards.addWidget(label("No deadlines yet. Add one, or load the sample week from the Demo tab.", muted=True))
        for d in deadlines:
            self.cards.addWidget(DeadlineCard(self, assess(d, state.working_style, now)))
        self.cards.addStretch(1)

    # actions

    def _run_estimate(self, fn: Callable[[], list[str]]) -> None:
        self.busy = True
        self.refresh(force=True)
        self.pool.start(Job(fn, self._estimate_done))

    def _estimate_done(self, errors) -> None:
        self.busy = False
        self.refresh(force=True)
        if errors:
            QMessageBox.warning(self, "Gameline", "\n".join(errors))

    def add_deadline(self) -> DeadlineModal:
        def save(title: str, due: datetime, notes: str) -> None:
            self._run_estimate(lambda: self.ctx.add_deadline(title, due, notes))

        return DeadlineModal(self.centralWidget(), self.ctx.clock.now(), save)

    def edit_deadline(self, d: Deadline) -> DeadlineModal:
        def save(title: str, due: datetime, notes: str) -> None:
            self._run_estimate(lambda: self.ctx.edit_deadline(d.id, title, due, notes))

        return DeadlineModal(self.centralWidget(), self.ctx.clock.now(), save, d)

    def delete_deadline(self, d: Deadline) -> ConfirmModal:
        def confirm() -> None:
            self.ctx.delete_deadline(d.id)
            self.refresh(force=True)

        return ConfirmModal(
            self.centralWidget(),
            "Delete deadline",
            f"Delete “{d.title}” and its work plan?",
            "This cannot be reversed!",
            "Delete",
            confirm,
        )

    def toggle_chunk(self, did: str, index: int, done: bool) -> None:
        self.ctx.set_chunk_done(did, index, done)
        # Defer the rebuild so the checkbox that fired this isn't deleted mid-signal.
        QTimer.singleShot(0, lambda: self.refresh(force=True))

    def _load_settings(self) -> None:
        state = self.ctx.store.load()
        ws = state.working_style
        self.style_box.setCurrentIndex(self.style_box.findData(ws.style))
        self.daily_hours.setValue(ws.daily_work_hours)
        self.max_minutes.setValue(ws.max_gaming_minutes)
        self.tags.setText(", ".join(state.tagged_games))

    def save_settings(self) -> None:
        style = WorkingStyle(
            style=self.style_box.currentData(),
            daily_work_hours=self.daily_hours.value(),
            max_gaming_minutes=self.max_minutes.value(),
        )
        self.ctx.save_settings(style, self.tags.text().split(","))
        self.statusBar().showMessage("Settings saved", 2500)
        self.refresh(force=True)

    def seed_demo(self) -> None:
        self.ctx.seed_demo_data()
        self._load_settings()
        self.refresh(force=True)

    def toggle_fake_game(self) -> None:
        if self.ctx.fake_game_running:
            self.ctx.stop_fake_game()
        else:
            self.ctx.start_fake_game()
        self.refresh(force=True)

    def closeEvent(self, event) -> None:
        # Closing the window keeps Gameline running in the menu bar.
        event.ignore()
        self.hide()
