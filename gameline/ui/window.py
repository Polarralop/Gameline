"""The main Gameline window: deadlines, settings and demo controls.

Qt patterns used here:
- Layouts (QVBoxLayout/QHBoxLayout/QFormLayout) position child widgets.
- Signals and slots: button.clicked.connect(fn) calls fn on click.
- Slow work (LLM estimates) runs on QThreadPool; a Signal carries the result
  back, because widgets may only be touched from the main (GUI) thread.
"""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from pathlib import Path

from PySide6.QtCore import (
    QDateTime,
    QEvent,
    QEasingCurve,
    QObject,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QRectF,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPen, QShortcut, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QApplication,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..context import AppContext
from ..llm import BACKENDS
from ..llm.claude_cli import AccountStatus, account_status, open_login_terminal
from ..llm.claude_cli import logout as claude_logout
from ..models import Deadline, NotifyLevel, Style, WorkingStyle, subject_of
from ..paths import icons_dir
from ..planner import DeadlineStatus, assess
from .theme import colors, dropdown_list_qss, icon_path

NOTIFY_LABELS = {
    NotifyLevel.OFF: "No notifications",
    NotifyLevel.NORMAL: "Standard",
    NotifyLevel.INTERRUPT: "Interrupting",
}

NOTIFY_HELP = (
    "<b>No notifications</b>: Gameline stays quiet. No launch reminders or break alerts; "
    "the menu bar dot and your deadline cards still show what's at risk.<br><br>"
    "<b>Standard</b>: a notification when you open a game while behind on a deadline, "
    "and break alerts once you pass your session limit.<br><br>"
    "<b>Interrupting</b>: like Standard, but break alerts also bring the Gameline window "
    "to the front, even over a fullscreen game."
)

STYLE_LABELS = {Style.SHORT_BURSTS: "Short bursts", Style.MIXED: "Mixed", Style.LONG_SESSIONS: "Long sessions"}


def bring_app_to_front() -> None:
    """Qt can raise a window but macOS won't switch to the app on its own, so
    ask AppKit directly. No-op elsewhere or if it isn't available."""
    if sys.platform != "darwin":
        return
    try:
        from rubicon.objc import ObjCClass

        ObjCClass("NSApplication").sharedApplication.activateIgnoringOtherApps_(True)
    except Exception:
        pass


def style_calendar(cal: QCalendarWidget) -> None:
    """Match the date picker to the theme: no red weekends, quieter weekday
    headers, chevron arrows, and no week-number column."""
    c = colors()
    cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
    cal.setGridVisible(False)
    plain = QTextCharFormat()
    plain.setForeground(QColor(c["ink"]))
    # Same format for every weekday, so weekend headers match the rest too.
    for day in Qt.DayOfWeek:
        cal.setWeekdayTextFormat(day, plain)
    header = QTextCharFormat()
    header.setForeground(QColor(c["muted"]))
    header.setBackground(QColor(c["card"]))
    cal.setHeaderTextFormat(header)
    cal.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
    for name, icon in (("qt_calendar_prevmonth", "chevron-left"), ("qt_calendar_nextmonth", "chevron-right")):
        btn = cal.findChild(QToolButton, name)
        if btn:
            btn.setIcon(QIcon(icon_path(icon, c["ink"])))
            btn.setIconSize(QSize(14, 14))
    cal.setMinimumSize(300, 250)


class _DropdownRowDelegate(QStyledItemDelegate):
    """Fixed row height, so the list lays out the same before and after styling."""

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), 32)


class HelpBadge(QWidget):
    """A small circled ? that explains a setting on hover. Painted by hand so
    the ? sits exactly in the middle (a styled QLabel nudges it off-centre)."""

    SIZE = 18

    def __init__(self, text: str) -> None:
        super().__init__()
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setToolTip(f"<div style='width: 280px'>{text}</div>")
        self.setCursor(Qt.CursorShape.WhatsThisCursor)
        self.setObjectName("help")
        self.hovered = False

    def enterEvent(self, event) -> None:
        self.hovered = True
        self.update()

    def leaveEvent(self, event) -> None:
        self.hovered = False
        self.update()

    def paintEvent(self, event) -> None:
        c = colors()
        color = QColor(c["ink"] if self.hovered else c["muted"])
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(color, 1.5)
        p.setPen(pen)
        r = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        p.drawEllipse(r)
        font = p.font()
        font.setPixelSize(11)
        font.setBold(True)
        p.setFont(font)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, "?")


def help_badge(text: str) -> HelpBadge:
    return HelpBadge(text)


def styled_combo() -> QComboBox:
    """A combo box whose popup list follows the stylesheet (the default view
    on macOS ignores per-item styling)."""
    box = QComboBox()
    view = QListView()
    view.setStyleSheet(dropdown_list_qss())
    box.setView(view)
    # The default combo delegate draws items like menu entries and ignores the
    # stylesheet; the standard delegate honours ::item padding, height and hover.
    box.setItemDelegate(_DropdownRowDelegate(box))
    # The list sits inside a popup window that paints its own square frame and
    # background. Make that window frameless and see-through, so only the
    # rounded list (styled in theme.py) shows.
    popup = box.view().window()
    popup.setWindowFlags(popup.windowFlags() | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
    popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    popup.setStyleSheet("QComboBoxPrivateContainer { background: transparent; border: none; }")
    return box


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
        # on_done should be a bound method of a QObject (a widget), so the
        # signal is queued onto the GUI thread rather than called from the pool.
        super().__init__()
        self.fn = fn
        self.signals = _JobSignals()
        self.signals.done.connect(on_done)

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:  # surface errors in the UI instead of dying silently
            result = [f"{exc.__class__.__name__}: {exc}"]
        try:
            self.signals.done.emit(result)
        except RuntimeError:
            pass  # the receiving window closed while this was running


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
        self.heading = label(heading, name="modalTitle")
        self.body.addWidget(self.heading)
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
        style_calendar(self.due.calendarWidget())
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
        on_cancel: Callable[[], None] | None = None,
        danger: bool = True,
    ) -> None:
        super().__init__(host, heading, width=420)
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self._confirmed = False
        self.body.addWidget(label(message, wrap=True))
        if warning:
            self.body.addWidget(label(warning, name="warning" if danger else "", muted=not danger, wrap=True))
        self.confirm_btn = self.add_buttons(confirm_text, self._confirm, danger=danger)
        self.open(focus=self.confirm_btn)

    def _confirm(self) -> None:
        self._confirmed = True
        self.close_modal()
        self.on_confirm()

    def close_modal(self) -> None:
        super().close_modal()
        if not self._confirmed and self.on_cancel:
            self.on_cancel()


class SyllabusModal(Modal):
    """Bulk add from a syllabus. Opens straight away in a "reading" state with a
    spinner, then shows the proposed deadlines as a checklist. Ones that look
    like existing deadlines are flagged and start unticked."""

    def __init__(self, host: QWidget, filename: str, on_add: Callable[[list], None]) -> None:
        super().__init__(host, "Reading syllabus", width=560)
        self.on_add = on_add
        self.closed = False
        self.content = QWidget()
        self.body.addWidget(self.content)
        lay = QVBoxLayout(self.content)
        lay.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(Spinner(18))
        row.addWidget(label(f"Reading {filename}…"), 1)
        lay.addLayout(row)
        lay.addWidget(label("Finding assignments, quizzes, tests and exams. This can take a minute.",
                            muted=True, wrap=True))
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setProperty("ghost", True)
        cancel.clicked.connect(self.close_modal)
        buttons.addWidget(cancel)
        lay.addSpacing(4)
        lay.addLayout(buttons)
        self.open()

    def close_modal(self) -> None:
        self.closed = True  # a result arriving later is ignored
        super().close_modal()

    def _replace_content(self) -> QVBoxLayout:
        self.content.hide()
        self.content.deleteLater()
        self.content = QWidget()
        self.body.addWidget(self.content)
        lay = QVBoxLayout(self.content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        return lay

    def _resize_card(self) -> None:
        # New content isn't measured until it's shown and laid out; do that
        # before resizing the card, or it keeps the old (smaller) size.
        self.content.show()
        self.body.activate()
        self._center_card()

    def show_error(self, message: str) -> None:
        self.heading.setText("Couldn't read that syllabus")
        lay = self._replace_content()
        lay.addWidget(label(message, wrap=True))
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("OK")
        ok.clicked.connect(self.close_modal)
        row.addWidget(ok)
        lay.addLayout(row)
        self._resize_card()

    def show_proposals(self, proposals: list) -> None:
        self.proposals = proposals
        n = len(proposals)
        if n == 0:
            self.show_error("No dated deadlines were found in that PDF.")
            return
        self.heading.setText(f"Found {n} deadline{'s' if n != 1 else ''}")
        lay = self._replace_content()
        dupes = sum(1 for p in proposals if p.duplicate_of)
        past = sum(1 for p in proposals if p.past and not p.duplicate_of)
        intro = "Untick anything you don't want to add."
        notes = []
        if dupes:
            notes.append(f"{dupes} already on your list")
        if past:
            notes.append(f"{past} already past")
        if notes:
            intro += f" Unticked to start: {' and '.join(notes)}."
        lay.addWidget(label(intro, muted=True, wrap=True))

        listing = QWidget()
        rows = QVBoxLayout(listing)
        rows.setContentsMargins(0, 0, 6, 0)
        rows.setSpacing(2)
        self.checks: list[QCheckBox] = []
        for prop in proposals:
            item = QFrame()
            item.setObjectName("proposal")
            h = QHBoxLayout(item)
            h.setContentsMargins(8, 6, 8, 6)
            h.setSpacing(10)
            box = QCheckBox()
            box.setChecked(prop.suggested)
            box.toggled.connect(self._update_count)
            box.setCursor(Qt.CursorShape.PointingHandCursor)
            self.checks.append(box)
            h.addWidget(box, 0, Qt.AlignmentFlag.AlignTop)
            text = QVBoxLayout()
            text.setSpacing(1)
            title = label(prop.title, name="task", wrap=True)
            title.setCursor(Qt.CursorShape.PointingHandCursor)
            title.mousePressEvent = lambda e, b=box: b.toggle()
            text.addWidget(title)
            meta = f"Due {fmt_dt(prop.due)}" + (f" · {prop.notes}" if prop.notes else "")
            text.addWidget(label(meta, muted=True, wrap=True))
            if prop.duplicate_of:
                text.addWidget(label(f"Looks like “{prop.duplicate_of}”, which is already on your list",
                                     name="warning", wrap=True))
            elif prop.past:
                text.addWidget(label("Already past", muted=True))
            h.addLayout(text, 1)
            rows.addWidget(item)
        rows.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(listing)
        for w_ in (scroll, scroll.viewport(), listing):
            w_.setObjectName("proposalList")  # transparent, so it sits on the card colour
        listing.adjustSize()
        scroll.setFixedHeight(min(360, listing.sizeHint().height() + 2))
        lay.addWidget(scroll)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setProperty("ghost", True)
        cancel.clicked.connect(self.close_modal)
        self.add_btn = QPushButton()
        self.add_btn.clicked.connect(self._add)
        buttons.addWidget(cancel)
        buttons.addWidget(self.add_btn)
        lay.addLayout(buttons)
        self._update_count()
        self._resize_card()

    def selected(self) -> list:
        return [p for p, box in zip(self.proposals, self.checks) if box.isChecked()]

    def _update_count(self) -> None:
        n = len(self.selected())
        self.add_btn.setText(f"Add {n} deadline{'s' if n != 1 else ''}")
        self.add_btn.setEnabled(n > 0)

    def _add(self) -> None:
        chosen = self.selected()
        self.close_modal()
        self.on_add(chosen)


class AlertModal(Modal):
    """A message with one button, for interrupting long-session alerts."""

    def __init__(self, host: QWidget, heading: str, message: str, button: str = "Got it") -> None:
        super().__init__(host, heading, width=420)
        self.body.addWidget(label(message, wrap=True))
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(button)
        ok.clicked.connect(self.close_modal)
        row.addWidget(ok)
        self.body.addSpacing(4)
        self.body.addLayout(row)
        self.ok_btn = ok
        self.open(focus=ok)


# --- spinner and toasts --------------------------------------------------------


class Spinner(QWidget):
    """Small rotating arc, shown while the AI is estimating."""

    def __init__(self, size: int = 16) -> None:
        super().__init__()
        self.setFixedSize(size, size)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def _tick(self) -> None:
        self.angle = (self.angle + 8) % 360
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(colors()["accent"]), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        r = self.rect().adjusted(2, 2, -2, -2)
        p.drawArc(r, -self.angle * 16, 270 * 16)


class Toast(QFrame):
    def __init__(self, host: QWidget, text: str, tone: str) -> None:
        super().__init__(host)
        self.setObjectName("toast")
        self.setProperty("tone", tone)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        msg = QLabel(text)
        msg.setWordWrap(True)
        lay.addWidget(msg)
        # Wrapped labels need their height worked out from the width up front,
        # after the stylesheet font is applied.
        self.ensurePolished()
        msg.ensurePolished()
        self.setFixedSize(320, msg.heightForWidth(320 - 31) + 22)
        self.fx = QGraphicsOpacityEffect(self)
        self.fx.setOpacity(0.0)
        self.setGraphicsEffect(self.fx)
        self.anim = QPropertyAnimation(self.fx, b"opacity", self)
        self.anim.setDuration(180)


class Toaster(QObject):
    """Stacks small auto-dismissing notices in the top-right of the window."""

    MARGIN, TOP, GAP = 16, 64, 8  # TOP sits just under the page header and status pill

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.host = host
        self.toasts: list[Toast] = []
        host.installEventFilter(self)

    def show(self, text: str, tone: str = "info", ms: int = 3000) -> Toast:
        toast = Toast(self.host, text, tone)
        self.toasts.append(toast)
        self._layout()
        toast.show()
        toast.raise_()
        toast.anim.setStartValue(0.0)
        toast.anim.setEndValue(1.0)
        toast.anim.start()
        QTimer.singleShot(ms, lambda: self._dismiss(toast))
        return toast

    def _dismiss(self, toast: Toast) -> None:
        if toast not in self.toasts:
            return
        toast.anim.stop()
        toast.anim.setStartValue(toast.fx.opacity())
        toast.anim.setEndValue(0.0)
        toast.anim.finished.connect(lambda: self._remove(toast))
        toast.anim.start()

    def _remove(self, toast: Toast) -> None:
        if toast in self.toasts:
            self.toasts.remove(toast)
            toast.deleteLater()
            self._layout()

    def _layout(self) -> None:
        y = self.TOP
        for t in self.toasts:
            t.move(self.host.width() - t.width() - self.MARGIN, y)
            t.raise_()
            y += t.height() + self.GAP

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Resize:
            self._layout()
        return False


# --- deadline card -----------------------------------------------------------


def _repolish(w: QWidget) -> None:
    """Re-apply the stylesheet after changing a property it selects on."""
    w.style().unpolish(w)
    w.style().polish(w)


class TaskRow(QWidget):
    """Checkbox, wrapping task title, and hours/time on the right. Clicking the
    title toggles the box too."""

    def __init__(self, chunk, on_toggle: Callable[[bool], None]) -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 3, 0, 3)
        row.setSpacing(10)
        self.box = QCheckBox()
        self.box.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(self.box, 0, Qt.AlignmentFlag.AlignTop)

        self.title = QLabel(chunk.title)
        self.title.setObjectName("task")
        self.title.setWordWrap(True)
        self.title.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title.mousePressEvent = lambda e: self.box.toggle()
        row.addWidget(self.title, 1)

        meta = f"{chunk.hours:g}h"
        if chunk.start:
            meta += f" · {chunk.start.strftime('%a %-I:%M %p')}"
        when = QLabel(meta)
        when.setObjectName("taskMeta")
        when.setContentsMargins(0, 2, 0, 0)  # line up with the larger title text
        row.addWidget(when, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        self.set_done(chunk.done)
        self.box.toggled.connect(self.set_done)
        self.box.toggled.connect(on_toggle)

    def set_done(self, done: bool) -> None:
        self.box.blockSignals(True)
        self.box.setChecked(done)
        self.box.blockSignals(False)
        if self.title.property("done") == done:
            return
        self.title.setProperty("done", done)
        font = self.title.font()
        font.setStrikeOut(done)
        self.title.setFont(font)
        _repolish(self.title)


class DeadlineCard(QFrame):
    """One deadline. Built once; ticks, collapsing and the clock moving update
    the existing widgets in place (update()), so nothing gets rebuilt or flashes."""

    def __init__(self, window: MainWindow, s: DeadlineStatus) -> None:
        super().__init__()
        self.setObjectName("card")
        self.window_ = window
        d = s.deadline
        self.did = d.id
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)

        self.complete_btn = None
        if d.completed:
            self._build_completed(window, d, lay)
            return

        top = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(2)
        left.addWidget(label(d.title, name="title"))
        self.meta = label("", muted=True)
        left.addWidget(self.meta)
        top.addLayout(left, 1)
        pending = d.id in window.pending
        self.estimated = d.estimate is not None and not d.needs_estimate
        self.pill = self.arrow = self.bar = self.stats = self.summary = self.details = None
        self.rows: list[TaskRow] = []
        if pending:
            thinking = QHBoxLayout()
            thinking.setSpacing(6)
            thinking.addWidget(Spinner())
            thinking.addWidget(label("Estimating…", muted=True))
            top.addLayout(thinking)
        elif not self.estimated:
            top.addWidget(pill("Not estimated", "idle"), 0, Qt.AlignmentFlag.AlignTop)
        else:
            self.pill = pill("", "ok")
            top.addWidget(self.pill, 0, Qt.AlignmentFlag.AlignTop)
            self.arrow = QToolButton()
            self.arrow.setObjectName("collapse")
            self.arrow.setIconSize(QSize(14, 14))
            self.arrow.setCursor(Qt.CursorShape.PointingHandCursor)
            self.arrow.clicked.connect(lambda: window.toggle_collapsed(d.id))
            top.addWidget(self.arrow, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(top)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        lay.addWidget(self.bar)

        if not self.estimated:
            # Placeholder until the estimate lands.
            if pending:
                fx = QGraphicsOpacityEffect(self)
                fx.setOpacity(0.55)
                self.setGraphicsEffect(fx)
            else:
                retry = QHBoxLayout()
                retry.addWidget(label("The estimate didn't come back.", muted=True))
                retry.addStretch(1)
                for text, fn in (("Retry", lambda: window.start_estimate(d.id)),
                                 ("Edit", lambda: window.edit_deadline(d)),
                                 ("Delete", lambda: window.delete_deadline(d))):
                    retry.addWidget(self._ghost(text, fn))
                lay.addLayout(retry)
            self.update_status(s)
            return

        self.stats = label("", muted=True)
        lay.addWidget(self.stats)

        # Rationale + task list live in one container that collapsing hides.
        self.details = QWidget()
        dl = QVBoxLayout(self.details)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(6)
        if d.estimate.rationale:
            dl.addWidget(label(d.estimate.rationale, muted=True, wrap=True))
        tasks = QVBoxLayout()
        tasks.setContentsMargins(0, 4, 0, 0)
        tasks.setSpacing(2)
        for i, c in enumerate(d.estimate.chunks):
            row = TaskRow(c, lambda on, i=i, did=d.id: window.toggle_chunk(did, i, on))
            self.rows.append(row)
            tasks.addWidget(row)
        dl.addLayout(tasks)
        lay.addWidget(self.details)

        actions = QHBoxLayout()
        self.summary = label("", muted=True)  # "2 of 8 tasks done", shown when collapsed
        actions.addWidget(self.summary)
        actions.addStretch(1)
        self.complete_btn = QPushButton("✓  Complete")
        self.complete_btn.setObjectName("complete")
        self.complete_btn.setToolTip("Mark this deadline done and archive it")
        self.complete_btn.clicked.connect(lambda: window.complete_deadline(d.id))
        actions.addWidget(self.complete_btn)
        actions.addWidget(self._ghost("Edit", lambda: window.edit_deadline(d)))
        actions.addWidget(self._ghost("Delete", lambda: window.delete_deadline(d)))
        lay.addLayout(actions)
        self.update_status(s)

    def _build_completed(self, window: MainWindow, d: Deadline, lay: QVBoxLayout) -> None:
        """Archived look: one compact row with Reopen and Delete."""
        self.setProperty("completed", True)
        self.estimated = False
        row = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(2)
        title = label(d.title, name="title")
        font = title.font()
        font.setStrikeOut(True)
        title.setFont(font)
        title.setProperty("done", True)
        left.addWidget(title)
        self.meta = label(f"Completed {fmt_dt(d.completed_at)} · was due {fmt_dt(d.due)}", muted=True)
        left.addWidget(self.meta)
        row.addLayout(left, 1)
        row.addWidget(pill("Completed", "idle"), 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self._ghost("Reopen", lambda: window.reopen_deadline(d.id)))
        row.addWidget(self._ghost("Delete", lambda: window.delete_deadline(d)))
        lay.addLayout(row)

    @staticmethod
    def _ghost(text: str, fn: Callable[[], object]) -> QPushButton:
        b = QPushButton(text)
        b.setProperty("ghost", True)
        b.clicked.connect(fn)
        return b

    def update_status(self, s: DeadlineStatus) -> None:
        d = s.deadline
        if d.completed:
            return
        if self.complete_btn is not None:
            # Highlight Complete once every task is ticked.
            ready = all(r.box.isChecked() for r in self.rows) and bool(self.rows)
            if self.complete_btn.property("ready") != ready:
                self.complete_btn.setProperty("ready", ready)
                _repolish(self.complete_btn)
        meta = f"Due {fmt_dt(d.due)}"
        if d.estimate and self.estimated:
            meta += f" · importance {d.estimate.importance}/5"
        self.meta.setText(meta)
        if not self.estimated:
            return

        tone = "risk" if s.at_risk else "ok"
        self.pill.setText("At risk" if s.at_risk else "On track")
        if self.pill.property("pill") != tone:
            self.pill.setProperty("pill", tone)
            _repolish(self.pill)
        have = s.available_hours
        self.bar.setValue(100 if have <= 0 else min(100, round(s.remaining_hours / have * 100)))
        if self.bar.property("tone") != tone:
            self.bar.setProperty("tone", tone)
            _repolish(self.bar)
        self.stats.setText(
            f"{s.remaining_hours:.1f}h of work left · {have:.1f}h realistically available · "
            f"slack {s.slack_hours:+.1f}h")
        for row, c in zip(self.rows, d.estimate.chunks):
            row.set_done(c.done)
        self.set_collapsed(d.id in self.window_.collapsed, d)

    def set_collapsed(self, collapsed: bool, d: Deadline | None = None) -> None:
        if self.details is None:
            return
        done = sum(r.box.isChecked() for r in self.rows)
        if getattr(self, "_shown", None) == (collapsed, done):
            return  # nothing changed; skip so the clock tick doesn't repaint
        self._shown = (collapsed, done)
        self.details.setVisible(not collapsed)
        self.summary.setVisible(collapsed)
        self.summary.setText(f"{done} of {len(self.rows)} tasks done")
        self.arrow.setIcon(QIcon(icon_path("chevron-right" if collapsed else "chevron-down", colors()["muted"])))
        self.arrow.setToolTip("Show tasks" if collapsed else "Hide tasks")


# --- tagged games list ---------------------------------------------------------


class GameList(QWidget):
    """Type an app name and press Enter (or Add) to tag it as a game. The
    collapsible list below shows tagged apps, each with a ✕ to remove it."""

    WIDTH = 320

    def __init__(self, on_add: Callable[[str], bool], on_remove: Callable[[str], None]) -> None:
        super().__init__()
        self.on_add, self.on_remove = on_add, on_remove
        self.expanded = True
        self.setFixedWidth(self.WIDTH)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type an app name, e.g. Minecraft")
        self.input.setFixedHeight(36)
        self.input.returnPressed.connect(self._add)
        add = QPushButton("Add")
        add.setFixedSize(64, 36)
        add.clicked.connect(self._add)
        row.addWidget(self.input, 1)
        row.addWidget(add)
        lay.addLayout(row)

        self.toggle = QPushButton()
        self.toggle.setObjectName("listToggle")
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.clicked.connect(self._toggle)
        lay.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignLeft)

        self.list = QFrame()
        self.list.setObjectName("gameList")
        self.rows = QVBoxLayout(self.list)
        self.rows.setContentsMargins(4, 4, 4, 4)
        self.rows.setSpacing(0)
        lay.addWidget(self.list)

    def set_games(self, games: list[str]) -> None:
        while self.rows.count():
            w = self.rows.takeAt(0).widget()
            if w:
                w.hide()
                w.deleteLater()
        for name in games:
            item = QFrame()
            item.setObjectName("gameItem")
            h = QHBoxLayout(item)
            h.setContentsMargins(10, 4, 4, 4)
            h.addWidget(QLabel(name), 1)
            x = QToolButton()
            x.setObjectName("removeGame")
            x.setText("✕")
            x.setToolTip(f"Stop treating {name} as a game")
            x.setCursor(Qt.CursorShape.PointingHandCursor)
            x.clicked.connect(lambda _=False, n=name: self.on_remove(n))
            h.addWidget(x)
            self.rows.addWidget(item)
        n = len(games)
        self.toggle.setVisible(n > 0)
        self._count = n
        self._apply()

    def _apply(self) -> None:
        n = getattr(self, "_count", 0)
        noun = "app" if n == 1 else "apps"
        self.toggle.setText(f"{'▾' if self.expanded else '▸'}  {n} {noun} tagged as games")
        self.list.setVisible(self.expanded and n > 0)

    def _toggle(self) -> None:
        self.expanded = not self.expanded
        self._apply()

    def _add(self) -> None:
        if self.on_add(self.input.text()):
            self.input.clear()
            self.expanded = True
            self._apply()


# --- sidebar -----------------------------------------------------------------

ICONS_DIR = icons_dir()  # repo assets/icons, or Gameline.app's Resources when packaged


def nav_icon(name: str) -> QIcon:
    """Sidebar icon from assets/icons, muted normally and ink when checked.
    The SVGs draw in currentColor, so we write a colored copy per theme color."""
    icon = QIcon()
    c = colors()
    for color, state in ((c["muted"], QIcon.State.Off), (c["ink"], QIcon.State.On)):
        path = Path(tempfile.gettempdir()) / f"gameline-nav-{name}-{color.lstrip('#')}.svg"
        path.write_text((ICONS_DIR / f"{name}.svg").read_text().replace("currentColor", color))
        icon.addFile(path.as_posix(), QSize(18, 18), QIcon.Mode.Normal, state)
    return icon


def menu_icon() -> QIcon:
    """Hamburger icon in the same 24px grid and stroke as the assets/icons set."""
    c = colors()
    path = Path(tempfile.gettempdir()) / f"gameline-menu-{c['muted'].lstrip('#')}.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
        f'stroke="{c["muted"]}" stroke-width="1.7" stroke-linecap="round">'
        '<path d="M4 7h16M4 12h16M4 17h16"/></svg>'
    )
    return QIcon(path.as_posix())


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
        self.toggle_btn = QPushButton(top)
        self.toggle_btn.setObjectName("navToggle")
        # Drawn as an icon with the same size and left padding as the nav icons
        # below it, so all of them line up on one vertical axis.
        self.toggle_btn.setIcon(menu_icon())
        self.toggle_btn.setIconSize(QSize(18, 18))
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
        btn.setIcon(nav_icon(icon))
        btn.setIconSize(QSize(18, 18))
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
        for btn, _, text in self.items:
            btn.setText(f"  {text}" if self.expanded else "")


# --- main window -------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext, sessions: Callable[[], list[str]]) -> None:
        super().__init__()
        self.ctx = ctx
        self.sessions = sessions  # names of games currently being played
        self.pending: set[str] = set()  # deadline ids being estimated right now
        self.collapsed: set[str] = set()  # deadline ids whose task list is hidden
        self.card_widgets: dict[str, DeadlineCard] = {}
        self._signature = None
        self.pool = QThreadPool.globalInstance()
        self.account_checker = account_status  # swapped out in tests

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
            ("calendar", "Deadlines", self._deadlines_tab(), False),
            ("chart", "Recap", self._recap_tab(), False),
            ("demo", "Demo", self._demo_tab(), False),
            ("gear", "Preferences", self._settings_tab(), True),
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
        self.toaster = Toaster(page)
        self.sidebar.select(0)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh(force=True)

    def _go_to(self, index: int, text: str) -> None:
        self.stack.setCurrentIndex(index)
        self.page_title.setText(text)
        if text == "Preferences":
            self.check_claude()
        if text == "Recap":
            self.recap_page.refresh(force=True)

    # pages

    def _recap_tab(self) -> QWidget:
        from .recap_page import RecapPage  # local import: recap_page uses helpers from this module

        self.recap_page = RecapPage(self.ctx, self._freeze)
        return self.recap_page

    def _deadlines_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(0, 14, 0, 0)
        bar = QHBoxLayout()
        self.add_btn = QPushButton("Add deadline")
        self.add_btn.clicked.connect(self.add_deadline)
        bar.addWidget(self.add_btn)
        bulk = QPushButton("Bulk add from syllabus")
        bulk.setObjectName("secondary")
        bulk.setToolTip("Pick a course syllabus PDF; Gameline proposes its deadlines for you to review")
        # A lambda, because clicked passes a `checked` bool that bulk_add would take as the path.
        bulk.clicked.connect(lambda: self.bulk_add())
        self.bulk_btn = bulk
        bar.addWidget(bulk)
        bar.addStretch(1)
        self.sort_box = styled_combo()
        self.sort_box.addItem("Sort by due date", "due")
        self.sort_box.addItem("Group by subject", "subject")
        self.sort_box.setFixedSize(180, 36)
        self.sort_box.currentIndexChanged.connect(
            lambda: (self.ctx.set_view(sort=self.sort_box.currentData()), self._arrange_cards()))
        self.show_done = QCheckBox("Show completed")
        self.show_done.setObjectName("viewToggle")
        self.show_done.toggled.connect(lambda on: (self.ctx.set_view(show_completed=on), self._arrange_cards()))
        state = self.ctx.store.load()
        for w_ in (self.sort_box, self.show_done):
            w_.blockSignals(True)  # setting saved values isn't a user change
        self.sort_box.setCurrentIndex(max(0, self.sort_box.findData(state.view_sort)))
        self.show_done.setChecked(state.show_completed)
        for w_ in (self.sort_box, self.show_done):
            w_.blockSignals(False)
        bar.addWidget(self.sort_box)
        bar.addSpacing(8)
        bar.addWidget(self.show_done)
        lay.addLayout(bar)
        lay.addSpacing(12)

        self.cards_host = QWidget()
        self.cards_host.setObjectName("page")
        self.cards = QVBoxLayout(self.cards_host)
        self.cards.setContentsMargins(0, 0, 4, 0)
        self.cards.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # Always reserve the scrollbar's width, so cards don't reflow (and flash)
        # the moment the list grows tall enough to scroll.
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scroll.setWidget(self.cards_host)
        self.scroll = scroll
        sb = scroll.verticalScrollBar()

        def mark_idle(_min: int, maximum: int) -> None:
            # Hide the handle while there's nothing to scroll (see theme.py).
            sb.setProperty("idle", maximum == 0)
            sb.style().unpolish(sb)
            sb.style().polish(sb)

        sb.rangeChanged.connect(mark_idle)
        mark_idle(0, 0)
        lay.addWidget(scroll, 1)
        return tab

    def _settings_tab(self) -> QWidget:
        # The page is taller than the window, so it scrolls.
        tab = QWidget()
        tab.setObjectName("page")
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner.setObjectName("page")
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        form = QFormLayout(inner)
        form.setContentsMargins(0, 16, 0, 16)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(12)
        self.style_box = styled_combo()
        for st, text in STYLE_LABELS.items():
            self.style_box.addItem(text, st)
        self.daily_hours = QDoubleSpinBox()
        self.daily_hours.setRange(0.5, 16)
        self.daily_hours.setSingleStep(0.5)
        self.daily_hours.setSuffix(" h")
        self.notify_box = styled_combo()
        for level, text in NOTIFY_LABELS.items():
            self.notify_box.addItem(text, level)
        self.notify_box.currentIndexChanged.connect(self._notify_changed)
        self.max_minutes = QSpinBox()
        self.max_minutes.setRange(15, 600)
        self.max_minutes.setSingleStep(15)
        self.max_minutes.setSuffix(" min")
        self.repeat_minutes = QSpinBox()
        self.repeat_minutes.setRange(5, 240)
        self.repeat_minutes.setSingleStep(5)
        self.repeat_minutes.setSuffix(" min")
        save = QPushButton("Save settings")
        save.clicked.connect(self.save_settings)

        form.addRow(label("YOUR ROUTINE", name="h2"))
        form.addRow("Working style", self.style_box)
        form.addRow("Work hours per day", self.daily_hours)
        notify_row = QWidget()
        nr = QHBoxLayout(notify_row)
        nr.setContentsMargins(0, 0, 0, 0)
        nr.setSpacing(10)
        nr.addWidget(self.notify_box)
        nr.addWidget(help_badge(NOTIFY_HELP))
        nr.addStretch(1)
        form.addRow("Notifications", notify_row)
        form.addRow("Gaming session limit", self.max_minutes)
        form.addRow("Repeat break alert every", self.repeat_minutes)
        form.addRow("", save)

        form.addRow(QLabel(""))
        form.addRow(label("GAMES", name="h2"))
        self.game_list = GameList(self._add_game, self._remove_game)
        form.addRow("Extra apps to treat as games", self.game_list)
        form.addRow("", label("Steam and Epic games are detected automatically.", muted=True))
        self._settings_form = form

        # --- AI estimates: backend choice + Claude account status -----------
        form.addRow(QLabel(""))
        form.addRow(label("AI ESTIMATES", name="h2"))
        self.backend_box = styled_combo()
        for key, text in BACKENDS.items():
            self.backend_box.addItem(text, key)
        self.backend_box.currentIndexChanged.connect(self._backend_changed)
        form.addRow("Estimate with", self.backend_box)

        self.claude_btn = QPushButton("Checking Claude…")
        self.claude_btn.setObjectName("claudeAccount")
        self.claude_btn.clicked.connect(self.claude_account_clicked)
        self.claude_btn.setMinimumHeight(36)
        self.claude_status = label("", muted=True)  # one line, so nothing gets clipped
        form.addRow("Claude account", self.claude_btn)
        form.addRow("", self.claude_status)

        # --- danger zone ------------------------------------------------------
        form.addRow(QLabel(""))
        form.addRow(label("DANGER ZONE", name="dangerTitle"))
        for text, detail, action in (
            ("Delete all deadlines", "Removes all active and completed deadlines.", "deadlines"),
            ("Delete game history", "Removes all game history.", "games"),
            ("Delete everything", "Remove all data; this is a fresh start.", "everything"),
        ):
            b = QPushButton(text)
            b.setObjectName("dangerButton")
            b.setFixedSize(220, 36)
            b.clicked.connect(lambda _=False, a=action: self.confirm_wipe(a))
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(14)
            h.addWidget(b)
            h.addWidget(label(detail, muted=True), 1)
            form.addRow("", row)

        # One consistent size for every field and button on the page.
        for w in (self.style_box, self.daily_hours, self.notify_box, self.max_minutes, self.repeat_minutes, save,
                  self.backend_box, self.claude_btn):
            w.setFixedSize(320, 36)
        for spin in (self.daily_hours, self.max_minutes, self.repeat_minutes):
            spin.lineEdit().setTextMargins(10, 0, 10, 0)  # spin boxes ignore stylesheet padding
        # Labels as tall as the fields, so they line up with the field text.
        for row in range(form.rowCount()):
            item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            if item and isinstance(item.widget(), QLabel) and item.widget().text():
                item.widget().setMinimumHeight(36)
                item.widget().setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                item.widget().setContentsMargins(0, 8, 0, 0)  # first line level with the field text

        self._claude_checking = False
        self._login_polls = 0
        self.login_timer = QTimer(self)
        self.login_timer.setInterval(6000)
        self.login_timer.timeout.connect(self._poll_login)
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

        if self.stack.currentWidget() is getattr(self, "recap_page", None):
            self.recap_page.refresh()  # no-op unless the saved data changed
        state = self.ctx.store.load()
        sig = self._cards_signature(state)
        if force or sig != self._signature:
            self._signature = sig
            self._rebuild_cards(now)
        else:
            for d in state.deadlines:
                card = self.card_widgets.get(d.id)
                if card:
                    card.update_status(assess(d, state.working_style, now))

    @staticmethod
    def _set_tone(widget: QWidget, tone: str) -> None:
        if widget.property("pill") == tone:
            return  # repolishing every tick would repaint for nothing
        widget.setProperty("pill", tone)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _cards_signature(self, state) -> tuple:
        """What forces a rebuild: which deadlines exist and their shape. Ticks,
        collapsing and the clock moving are applied in place instead."""
        return tuple(
            (d.id, d.fingerprint(), d.estimate is not None and not d.needs_estimate,
             len(d.estimate.chunks) if d.estimate else 0, d.estimate.rationale if d.estimate else "",
             d.id in self.pending, d.completed)
            for d in sorted(state.deadlines, key=lambda d: d.due)
        )

    def _freeze(self, frozen: bool) -> None:
        """Pause painting for the whole window while cards move, so no
        half-arranged frame (e.g. the gap a hidden card leaves) ever shows.
        Nested calls are counted; painting resumes when the outermost ends."""
        self._freeze_depth = getattr(self, "_freeze_depth", 0) + (1 if frozen else -1)
        if frozen and self._freeze_depth == 1:
            self.setUpdatesEnabled(False)
        elif not frozen and self._freeze_depth == 0:
            # Layouts are lazy: the list's new height and the scroll area's
            # range are only worked out on the next event-loop pass. Do that
            # now, while still frozen; otherwise a scrolled-down list paints
            # once with the old geometry and flashes.
            self.cards.activate()
            QApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
            # Resume straight away. (A zero-delay timer here could sit unfired
            # on macOS until the next mouse event, so a page appeared only on
            # a second click.)
            self._unfreeze()

    def _unfreeze(self) -> None:
        if getattr(self, "_freeze_depth", 0) == 0:
            self.setUpdatesEnabled(True)
            # On macOS re-enabling updates doesn't schedule a repaint by itself,
            # so the new page only appeared on the next tick or click. Ask now.
            self.update()
            if self.centralWidget():
                self.centralWidget().update()

    def _rebuild_cards(self, now: datetime) -> None:
        """Recreate every card (deadlines added, deleted or re-estimated)."""
        self._freeze(True)  # paint once at the end
        try:
            for card in self.card_widgets.values():
                self.cards.removeWidget(card)
                card.hide()  # hide now; deleteLater only runs on the next event loop pass
                card.deleteLater()
            state = self.ctx.store.load()
            self.card_widgets = {
                d.id: DeadlineCard(self, assess(d, state.working_style, now)) for d in state.deadlines
            }
            self._arrange_cards(state)
        finally:
            self._freeze(False)

    def replace_card(self, did: str) -> None:
        """Recreate one card (it was completed or reopened) and re-place it."""
        state = self.ctx.store.load()
        d = state.get(did)
        old = self.card_widgets.get(did)
        if d is None or old is None:
            self.refresh(force=True)
            return
        self._freeze(True)
        try:
            self.cards.removeWidget(old)
            old.hide()
            old.deleteLater()
            self.card_widgets[did] = DeadlineCard(self, assess(d, state.working_style, self.ctx.clock.now()))
            self._arrange_cards(state)
        finally:
            self._freeze(False)
        self._signature = self._cards_signature(state)  # so the timer doesn't rebuild everything

    def _arrange_cards(self, state=None) -> None:
        """Order, group and show/hide the existing cards for the current view.
        Cards are only moved, never recreated, so changing the view doesn't flash."""
        state = state or self.ctx.store.load()
        self._freeze(True)
        try:
            # Take everything out of the layout. Cards, subject headers and the
            # empty-state note are all kept and reused, so nothing gets recreated.
            if not hasattr(self, "_headers"):
                self._headers: dict[str, QLabel] = {}
                self._empty_note = label("", muted=True)
            while self.cards.count():
                self.cards.takeAt(0)
            used_headers = set()

            hidden = 0 if state.show_completed else sum(d.completed for d in state.deadlines)
            shown = [d for d in state.deadlines if (state.show_completed or not d.completed) and d.id in self.card_widgets]
            shown.sort(key=lambda d: (d.completed, d.due))  # open first by due date, completed after
            for d in state.deadlines:
                card = self.card_widgets.get(d.id)
                if card is not None and card.isVisibleTo(self.cards_host) != (d in shown):
                    card.setVisible(d in shown)
            if not shown:
                text = "No deadlines yet. Add one, or load the sample week from the Demo tab."
                if hidden:
                    text = f"All caught up. {hidden} completed deadline{'s are' if hidden != 1 else ' is'} hidden."
                self._empty_note.setText(text)
                self.cards.addWidget(self._empty_note)
            self._empty_note.setVisible(not shown)

            if state.view_sort == "subject":
                groups: dict[str, list[Deadline]] = {}
                for d in shown:
                    groups.setdefault(subject_of(d.title), []).append(d)
                # Subjects ordered by their soonest open deadline; "Other" last.
                order = sorted(groups, key=lambda k: (k == "Other", min((g.completed, g.due) for g in groups[k])))
                for i, subject in enumerate(order):
                    header = self._headers.get(subject)
                    if header is None:
                        header = self._headers[subject] = label(subject.upper(), name="h2")
                    header.setContentsMargins(2, 8 if i else 0, 0, 0)
                    self.cards.addWidget(header)
                    used_headers.add(subject)
                    for d in groups[subject]:
                        self.cards.addWidget(self.card_widgets[d.id])
            else:
                for d in shown:
                    self.cards.addWidget(self.card_widgets[d.id])
            # Only touch visibility where it actually changes.
            for subject, header in self._headers.items():
                if header.isVisibleTo(self.cards_host) != (subject in used_headers):
                    header.setVisible(subject in used_headers)
            # Hidden (completed) cards stay parented but out of the layout.
            self.cards.addStretch(1)
        finally:
            self._freeze(False)

    # actions

    def toast(self, text: str, tone: str = "info", ms: int = 3000) -> None:
        self.toaster.show(text, tone, ms)

    def start_estimate(self, did: str) -> None:
        """Estimate in the background; the card shows a spinner until it lands."""
        if did in self.pending:
            return
        self.pending.add(did)
        self.refresh(force=True)
        # on_done must be a bound method of a QObject: Qt then delivers it on the
        # GUI thread. A lambda would run on the worker thread instead.
        self.pool.start(Job(lambda: (did, self.ctx.estimate_deadline(did)), self._estimate_done))

    def _estimate_done(self, result) -> None:
        if isinstance(result, list):  # the job itself crashed; Job returns the error text
            self.toast("\n".join(result), "error", ms=7000)
            self.pending.clear()
            self.refresh(force=True)
            return
        did, errors = result
        self.pending.discard(did)
        self.refresh(force=True)
        if errors:
            self.toast("\n".join(errors), "error", ms=7000)
        else:
            d = self.ctx.store.load().get(did)
            if d and d.estimate:
                self.toast(f"Estimated “{d.title}”: {d.estimate.effort_hours:g}h of work", "ok")

    def add_deadline(self) -> DeadlineModal:
        def save(title: str, due: datetime, notes: str) -> None:
            self.start_estimate(self.ctx.create_deadline(title, due, notes))

        return DeadlineModal(self.centralWidget(), self.ctx.clock.now(), save)

    def bulk_add(self, path: str | None = None) -> SyllabusModal | None:
        """Pick a syllabus PDF, read it in the background, then review proposals."""
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, "Choose a syllabus PDF", str(Path.home() / "Downloads"), "PDF files (*.pdf)")
            if not path:
                return None
        self._syllabus = SyllabusModal(self.centralWidget(), Path(path).name, self._add_proposals)
        self.pool.start(Job(lambda: ("ok", self.ctx.read_syllabus(path)), self._syllabus_done))
        return self._syllabus

    def _syllabus_done(self, result) -> None:
        modal = getattr(self, "_syllabus", None)
        if modal is None or modal.closed:
            return  # cancelled while reading
        if isinstance(result, tuple):
            modal.show_proposals(result[1])
        else:  # Job hands back error text on failure
            modal.show_error(" ".join(result))

    def _add_proposals(self, proposals: list) -> None:
        for p in proposals:
            self.start_estimate(self.ctx.create_deadline(p.title, p.due, p.notes))
        if proposals:
            n = len(proposals)
            self.toast(f"Added {n} deadline{'s' if n != 1 else ''}; estimating now", "ok")

    def edit_deadline(self, d: Deadline) -> DeadlineModal:
        def save(title: str, due: datetime, notes: str) -> None:
            if self.ctx.update_deadline(d.id, title, due, notes):
                self.start_estimate(d.id)
            else:
                self.refresh(force=True)
                self.toast("Deadline saved")

        return DeadlineModal(self.centralWidget(), self.ctx.clock.now(), save, d)

    def delete_deadline(self, d: Deadline) -> ConfirmModal:
        def confirm() -> None:
            self.ctx.delete_deadline(d.id)
            self.refresh(force=True)
            self.toast(f"Deleted “{d.title}”")

        return ConfirmModal(
            self.centralWidget(),
            "Delete deadline",
            f"Delete “{d.title}” and its work plan?",
            "This cannot be reversed!",
            "Delete",
            confirm,
        )

    def complete_deadline(self, did: str) -> ConfirmModal | None:
        d = self.ctx.store.load().get(did)
        if d is None:
            return None
        chunks = d.estimate.chunks if d.estimate else []
        left = sum(not c.done for c in chunks)

        def finish(check_all: bool) -> None:
            self.ctx.complete_deadline(did, check_all=check_all)
            self.replace_card(did)
            self.refresh()
            note = "" if self.ctx.store.load().show_completed else " Find it under Show completed."
            self.toast(f"Completed “{d.title}”.{note}", "ok")

        if left == 0:
            finish(False)
            return None
        return ConfirmModal(
            self.centralWidget(),
            "Not everything's finished",
            f"{left} of {len(chunks)} tasks for “{d.title}” {'is' if left == 1 else 'are'} still unchecked. "
            "Check them all and mark the deadline complete?",
            "",
            "Check all and complete",
            lambda: finish(True),
            danger=False,
        )

    def reopen_deadline(self, did: str) -> None:
        self.ctx.reopen_deadline(did)
        self.replace_card(did)
        self.refresh()
        self.toast("Deadline reopened")

    def toggle_collapsed(self, did: str) -> None:
        self.collapsed.symmetric_difference_update({did})
        card = self.card_widgets.get(did)
        if card:
            card.set_collapsed(did in self.collapsed)

    def toggle_chunk(self, did: str, index: int, done: bool) -> None:
        self.ctx.set_chunk_done(did, index, done)
        self.refresh()  # updates this card's bar, stats and pill in place

    WIPES = {
        "deadlines": ("Delete all deadlines?",
                      "Every deadline, open and completed, and all of their tasks will be removed. "
                      "Your recaps lose the work history that came from them."),
        "games": ("Delete game history?",
                  "Every recorded gaming session will be removed, so your recaps lose their "
                  "gaming totals. Preferences, tagged games and deadlines are kept."),
        "everything": ("Delete everything?",
                       "All deadlines, gaming history, tagged games and preferences will be removed. "
                       "Gameline starts fresh."),
    }

    def confirm_wipe(self, what: str) -> ConfirmModal:
        heading, message = self.WIPES[what]

        def wipe() -> None:
            if what == "deadlines":
                n = self.ctx.delete_all_deadlines()
                self.toast(f"Deleted {n} deadline{'s' if n != 1 else ''}", "ok")
            elif what == "games":
                n = self.ctx.delete_game_history()
                self.toast(f"Deleted {n} gaming session{'s' if n != 1 else ''}", "ok")
            else:
                self.ctx.delete_everything()
                self.toast("Everything deleted. Gameline starts fresh.", "ok")
            self.collapsed.clear()
            self._load_settings()
            self.refresh(force=True)

        return ConfirmModal(self.centralWidget(), heading, message,
                            "This can't be reversed!", "Delete", wipe)

    def _load_settings(self) -> None:
        state = self.ctx.store.load()
        ws = state.working_style
        self.style_box.setCurrentIndex(self.style_box.findData(ws.style))
        self.daily_hours.setValue(ws.daily_work_hours)
        self.max_minutes.setValue(ws.max_gaming_minutes)
        self.repeat_minutes.setValue(ws.repeat_minutes)
        self.notify_box.blockSignals(True)
        self.notify_box.setCurrentIndex(self.notify_box.findData(ws.notify_level))
        self.notify_box.blockSignals(False)
        self._notify_level = ws.notify_level
        for w in (self.max_minutes, self.repeat_minutes):
            w.setEnabled(ws.notify_level != NotifyLevel.OFF)
        self.game_list.set_games(state.tagged_games)
        self.backend_box.blockSignals(True)
        self.backend_box.setCurrentIndex(max(0, self.backend_box.findData(self.ctx.backend_name())))
        self.backend_box.blockSignals(False)

    def save_settings(self) -> None:
        style = WorkingStyle(
            style=Style(self.style_box.currentData()),
            daily_work_hours=self.daily_hours.value(),
            max_gaming_minutes=self.max_minutes.value(),
            repeat_minutes=self.repeat_minutes.value(),
        )
        self.ctx.save_settings(style)
        self.toast("Settings saved", "ok")
        self.refresh(force=True)

    # Notifications and games

    def _notify_changed(self) -> None:
        level = NotifyLevel(self.notify_box.currentData())  # Qt returns the enum as a str
        if level == NotifyLevel.INTERRUPT and self._notify_level != NotifyLevel.INTERRUPT:
            ConfirmModal(
                self.centralWidget(),
                "Turn on interrupting notifications?",
                "When a gaming session runs past your limit, Gameline will bring its window to the "
                "front, even over a fullscreen game. Launch reminders stay as normal notifications.",
                "This can interrupt online games or intense moments.",
                "Turn on",
                lambda: self._apply_notify(NotifyLevel.INTERRUPT),
                on_cancel=self._revert_notify,
            )
            return
        self._apply_notify(level)

    def _revert_notify(self) -> None:
        self.notify_box.blockSignals(True)
        self.notify_box.setCurrentIndex(self.notify_box.findData(self._notify_level))
        self.notify_box.blockSignals(False)

    def _apply_notify(self, level: NotifyLevel) -> None:
        self._notify_level = level
        self.ctx.set_notify_level(level)
        for w in (self.max_minutes, self.repeat_minutes):
            w.setEnabled(level != NotifyLevel.OFF)
        self.toast(f"Notifications: {NOTIFY_LABELS[level]}", "ok")

    def _add_game(self, name: str) -> bool:
        if not name.strip():
            return False
        if not self.ctx.add_tagged_game(name):
            self.toast(f"{name.strip()} is already on the list")
            return False
        self.game_list.set_games(self.ctx.store.load().tagged_games)
        self.toast(f"{name.strip()} will be treated as a game", "ok")
        return True

    def _remove_game(self, name: str) -> None:
        self.ctx.remove_tagged_game(name)
        self.game_list.set_games(self.ctx.store.load().tagged_games)
        self.toast(f"Removed {name}")

    def interrupt(self, title: str, body: str) -> None:
        """Interrupting level: bring Gameline to the front and show the alert in a modal."""
        self.showNormal()
        self.raise_()
        self.activateWindow()
        bring_app_to_front()
        self.sidebar.select(0)
        AlertModal(self.centralWidget(), title, body, "Taking a break")

    # Claude account

    def _backend_changed(self) -> None:
        self.ctx.set_backend(self.backend_box.currentData())
        self.toast(f"Estimates now use: {self.backend_box.currentText()}")

    def check_claude(self) -> None:
        """Ask the CLI for login status (plus a tiny test call) off the GUI thread."""
        if self._claude_checking:
            return
        self._claude_checking = True
        self._show_claude(None)
        self.pool.start(Job(self.account_checker, self._claude_checked))

    def _claude_checked(self, status) -> None:
        self._claude_checking = False
        if isinstance(status, AccountStatus):
            self._show_claude(status)
            if status.ok and self.login_timer.isActive():
                self.login_timer.stop()
                self.toast("Logged in to Claude", "ok")
        else:  # Job returns a list of error strings on failure
            self._show_claude(AccountStatus(installed=True, message="; ".join(status)))

    def _show_claude(self, status: AccountStatus | None) -> None:
        self.claude_account = status
        btn = self.claude_btn
        if status is None:
            text, tone, enabled = ("Waiting for login…" if self.login_timer.isActive() else "Checking Claude…"), "idle", False
        elif not status.installed:
            text, tone, enabled = "Claude Code not installed", "idle", False
        elif status.ok:
            text, tone, enabled = "✓  Logged in to Claude", "ok", True
        else:
            text, tone, enabled = "Log in to Claude", "action", True
        btn.setText(text)
        btn.setEnabled(enabled)
        btn.setProperty("tone", tone)
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        if status is None:
            self.claude_status.setText("")
        elif status.ok:
            who = status.email + (f" · {status.plan.title()}" if status.plan else "")
            self.claude_status.setText(who)
            btn.setToolTip("Click to log out")
        else:
            show = status.message and status.installed and "expired" not in status.label.lower()
            detail = f" ({status.message})" if show else ""
            self.claude_status.setText(status.label + detail)

    def claude_account_clicked(self) -> None:
        status = self.claude_account
        if status and status.ok:
            def do_logout() -> None:
                self.pool.start(Job(lambda: (claude_logout(), account_status(verify=False))[1], self._claude_checked))

            ConfirmModal(
                self.centralWidget(),
                "Log out of Claude",
                "Log Claude Code on this Mac out of your account?",
                "This also logs out the claude command in your terminal.",
                "Log out",
                do_logout,
            )
            return
        open_login_terminal()
        self._login_polls = 0
        self.login_timer.start()
        self._show_claude(None)

    def _poll_login(self) -> None:
        self._login_polls += 1
        if self._login_polls > 30:  # about 3 minutes
            self.login_timer.stop()
        self.check_claude()

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
