"""Recap page: weekly or monthly look back at work done and time spent gaming.

Work vs gaming share one unit (hours), so they share one axis in a grouped
bar chart. Colours are validated categorical slots (blue = work, orange =
gaming) for each theme; text stays in the ink colours, never the series colour.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import timedelta

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ..context import AppContext
from ..recap import Recap, build
from .theme import colors, icon_path
from .window import label, pill

LEVEL_TEXT = {"light": "Light", "medium": "Medium", "heavy": "Heavy"}


def _hours(h: float) -> str:
    if h <= 0:
        return "0h"
    return f"{round(h * 60)}m" if h < 1 else f"{h:.1f}h"


class BarChart(QWidget):
    """Grouped bars (work, gaming) per day or week, with a hover tooltip."""

    LEFT, BOTTOM, TOP = 40, 26, 10

    def __init__(self) -> None:
        super().__init__()
        self.recap: Recap | None = None
        self.setMinimumHeight(220)
        self.setMouseTracking(True)

    def set_recap(self, recap: Recap) -> None:
        self.recap = recap
        self.update()

    def _scale(self) -> tuple[float, int]:
        """Axis top and tick count, with round tick values (0.5h, 1h, 2h, 5h...)."""
        peak = max([max(b.work_hours, b.game_hours) for b in self.recap.buckets] + [1.0])
        for step in (0.5, 1, 2, 3, 5, 10, 20, 50):
            ticks = math.ceil(peak / step)
            if ticks <= 5:
                return step * ticks, ticks
        return peak, 4

    def _slots(self) -> list[QRectF]:
        n = len(self.recap.buckets)
        w = (self.width() - self.LEFT) / n
        return [QRectF(self.LEFT + i * w, self.TOP, w, self.height() - self.TOP - self.BOTTOM) for i in range(n)]

    def paintEvent(self, event) -> None:
        if not self.recap:
            return
        c = colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot_h = self.height() - self.TOP - self.BOTTOM
        base_y = self.TOP + plot_h
        top, ticks = self._scale()
        small = QFont(self.font())
        small.setPixelSize(11)
        p.setFont(small)

        # Recessive grid and y labels.
        for i in range(ticks + 1):
            v = top * i / ticks
            y = base_y - plot_h * i / ticks
            p.setPen(QPen(QColor(c["line"]), 1))
            p.drawLine(QPointF(self.LEFT, y), QPointF(self.width(), y))
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(0, y - 8, self.LEFT - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{v:g}h")

        # Bars: two per slot, 2px surface gap, 4px rounded tops anchored to the baseline.
        for slot, b in zip(self._slots(), self.recap.buckets):
            bar_w = min(22.0, (slot.width() - 14) / 2)
            x0 = slot.center().x() - bar_w - 1
            for i, (value, key) in enumerate(((b.work_hours, "series_work"), (b.game_hours, "series_game"))):
                if value <= 0:
                    continue
                h = max(2.0, plot_h * value / top)
                r = QRectF(x0 + i * (bar_w + 2), base_y - h, bar_w, h)
                path = QPainterPath()
                rad = min(4.0, h / 2, bar_w / 2)
                path.moveTo(r.left(), r.bottom())
                path.lineTo(r.left(), r.top() + rad)
                path.quadTo(r.left(), r.top(), r.left() + rad, r.top())
                path.lineTo(r.right() - rad, r.top())
                path.quadTo(r.right(), r.top(), r.right(), r.top() + rad)
                path.lineTo(r.right(), r.bottom())
                path.closeSubpath()
                p.fillPath(path, QColor(c[key]))
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(slot.left(), base_y + 6, slot.width(), 16), Qt.AlignmentFlag.AlignHCenter, b.label)

        # Baseline on top of the bars.
        p.setPen(QPen(QColor(c["muted"]), 1))
        p.drawLine(QPointF(self.LEFT, base_y), QPointF(self.width(), base_y))

    def mouseMoveEvent(self, event) -> None:
        if not self.recap:
            return
        pos = event.position()
        for slot, b in zip(self._slots(), self.recap.buckets):
            if slot.left() <= pos.x() < slot.right():
                when = b.start.strftime("%a %b %-d") if self.recap.kind == "week" else f"Week of {b.label}"
                QToolTip.showText(event.globalPosition().toPoint(),
                                  f"<b>{when}</b><br>Work: {_hours(b.work_hours)}<br>Gaming: {_hours(b.game_hours)}", self)
                return
        QToolTip.hideText()


class Tile(QFrame):
    """A headline number with a caption and an optional pill."""

    def __init__(self, caption: str) -> None:
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(2)
        lay.addWidget(label(caption.upper(), name="h2"))
        row = QHBoxLayout()
        self.value = QLabel()
        self.value.setObjectName("stat")
        row.addWidget(self.value)
        row.addStretch(1)
        self.badge = pill("", "idle")
        self.badge.hide()
        row.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(row)
        self.detail = label("", muted=True)
        lay.addWidget(self.detail)


class RecapPage(QWidget):
    def __init__(self, ctx: AppContext, freeze: Callable[[bool], None]) -> None:
        super().__init__()
        self.ctx = ctx
        self.freeze = freeze
        self.kind = "week"
        self.offset = 0  # 0 = this week/month, -1 = the one before, ...
        self._mtime = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 14, 0, 0)

        # Period controls: Week | Month, then ‹ label ›.
        bar = QHBoxLayout()
        self.seg = {}
        seg_frame = QFrame()
        seg_frame.setObjectName("segment")
        seg = QHBoxLayout(seg_frame)
        seg.setContentsMargins(3, 3, 3, 3)
        seg.setSpacing(2)
        for kind, text in (("week", "Week"), ("month", "Month")):
            b = QPushButton(text)
            b.setObjectName("segButton")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=kind: self.set_kind(k))
            seg.addWidget(b)
            self.seg[kind] = b
        bar.addWidget(seg_frame)
        bar.addSpacing(12)
        self.prev_btn = self._nav("chevron-left", "Earlier", -1)
        self.next_btn = self._nav("chevron-right", "Later", 1)
        bar.addWidget(self.prev_btn)
        self.period = label("", name="title")
        bar.addWidget(self.period)
        bar.addWidget(self.next_btn)
        bar.addStretch(1)
        outer.addLayout(bar)
        outer.addSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("page")
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 4, 12)
        lay.setSpacing(12)

        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.work_tile = Tile("Work done")
        self.game_tile = Tile("Gaming")
        self.done_tile = Tile("Finished")
        for t in (self.work_tile, self.game_tile, self.done_tile):
            tiles.addWidget(t, 1)
        lay.addLayout(tiles)

        chart_card = QFrame()
        chart_card.setObjectName("card")
        cl = QVBoxLayout(chart_card)
        cl.setContentsMargins(16, 14, 16, 12)
        head = QHBoxLayout()
        self.chart_title = label("", name="title")
        head.addWidget(self.chart_title)
        head.addStretch(1)
        c = colors()
        for text, key in (("Work", "series_work"), ("Gaming", "series_game")):
            sw = QLabel()
            sw.setFixedSize(10, 10)
            sw.setStyleSheet(f"background: {c[key]}; border-radius: 2px;")
            head.addWidget(sw)
            head.addWidget(label(text, muted=True))
            head.addSpacing(8)
        cl.addLayout(head)
        self.chart = BarChart()
        cl.addWidget(self.chart)
        lay.addWidget(chart_card)

        lower = QGridLayout()
        lower.setHorizontalSpacing(12)
        self.games_card, self.games_list = self._list_card("Games that hooked you")
        self.done_card, self.done_list = self._list_card("Deadlines completed")
        lower.addWidget(self.games_card, 0, 0)
        lower.addWidget(self.done_card, 0, 1)
        lower.setColumnStretch(0, 1)
        lower.setColumnStretch(1, 1)
        lay.addLayout(lower)
        lay.addStretch(1)

    def _nav(self, icon: str, tip: str, step: int) -> QToolButton:
        b = QToolButton()
        b.setObjectName("collapse")
        b.setIcon(QIcon(icon_path(icon, colors()["ink"])))
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda: self.shift(step))
        return b

    def _list_card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        lay.addWidget(label(title, name="title"))
        rows = QVBoxLayout()
        rows.setSpacing(8)
        lay.addLayout(rows)
        lay.addStretch(1)
        return card, rows

    # --- state -------------------------------------------------------------

    def set_kind(self, kind: str) -> None:
        self.kind, self.offset = kind, 0
        self.refresh(force=True)

    def shift(self, step: int) -> None:
        self.offset = min(0, self.offset + step)
        self.refresh(force=True)

    def refresh(self, force: bool = False) -> None:
        """Recompute when the data changed (or when asked)."""
        path = self.ctx.store.path
        mtime = path.stat().st_mtime if path.exists() else 0
        if not force and mtime == self._mtime:
            return
        self._mtime = mtime
        recap = build(self.ctx.store.load(), self.kind, self.ctx.clock.now(), self.offset)
        self.freeze(True)
        try:
            self._show(recap)
        finally:
            self.freeze(False)

    def _period_text(self, r: Recap) -> str:
        if r.kind == "week":
            last = r.end - timedelta(days=1)
            span = f"{r.start.strftime('%b %-d')} – {last.strftime('%b %-d')}"
            name = {0: "This week", -1: "Last week"}.get(self.offset, f"{-self.offset} weeks ago")
            return f"{name} · {span}"
        name = {0: "This month", -1: "Last month"}.get(self.offset, "")
        month = r.start.strftime("%B %Y")
        return f"{name} · {month}" if name else month

    def _show(self, r: Recap) -> None:
        for kind, b in self.seg.items():
            b.setChecked(kind == r.kind)
        self.next_btn.setEnabled(self.offset < 0)
        self.period.setText(self._period_text(r))
        unit = "week" if r.kind == "week" else "month"

        self.work_tile.value.setText(_hours(r.work_hours))
        self.work_tile.badge.setText(f"{LEVEL_TEXT[r.level]} {unit}")
        self.work_tile.badge.setProperty("pill", {"light": "idle", "medium": "ok", "heavy": "risk"}[r.level])
        self.work_tile.badge.style().unpolish(self.work_tile.badge)
        self.work_tile.badge.style().polish(self.work_tile.badge)
        self.work_tile.badge.show()
        self.work_tile.detail.setText(f"{r.tasks_done} task{'s' if r.tasks_done != 1 else ''} ticked off")

        self.game_tile.value.setText(_hours(r.game_hours))
        top = r.games[0].name if r.games else None
        self.game_tile.detail.setText(
            f"{r.sessions} session{'s' if r.sessions != 1 else ''}" + (f" · mostly {top}" if top else ""))

        n = len(r.deadlines_done)
        self.done_tile.value.setText(str(n))
        self.done_tile.detail.setText(f"deadline{'s' if n != 1 else ''} completed")

        self.chart_title.setText("Work vs gaming, by day" if r.kind == "week" else "Work vs gaming, by week")
        self.chart.set_recap(r)
        self._fill_games(r)
        self._fill_done(r)

    @staticmethod
    def _clear(rows: QVBoxLayout) -> None:
        while rows.count():
            item = rows.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def _fill_games(self, r: Recap) -> None:
        self._clear(self.games_list)
        if not r.games:
            self.games_list.addWidget(label("No gaming sessions recorded.", muted=True))
            return
        most = r.games[0].minutes or 1
        c = colors()
        for g in r.games[:6]:
            row = QWidget()
            v = QVBoxLayout(row)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(4)
            top = QHBoxLayout()
            top.addWidget(QLabel(g.name), 1)
            top.addWidget(label(f"{_hours(g.minutes / 60)} · {g.sessions} session{'s' if g.sessions != 1 else ''}",
                                muted=True))
            v.addLayout(top)
            track = QFrame()
            track.setFixedHeight(6)
            track.setStyleSheet(f"background: {c['line']}; border-radius: 3px;")
            fill = QFrame(track)
            fill.setStyleSheet(f"background: {c['series_game']}; border-radius: 3px;")
            fill.setProperty("ratio", g.minutes / most)
            track.resizeEvent = lambda e, f=fill, t=track: f.setGeometry(
                0, 0, max(6, int(t.width() * f.property("ratio"))), 6)
            v.addWidget(track)
            self.games_list.addWidget(row)

    def _fill_done(self, r: Recap) -> None:
        self._clear(self.done_list)
        if not r.deadlines_done:
            self.done_list.addWidget(label("Nothing completed in this period yet.", muted=True))
            return
        for title in r.deadlines_done:
            row = QHBoxLayout()
            w = QWidget()
            w.setLayout(row)
            row.setContentsMargins(0, 0, 0, 0)
            tick = QLabel("✓")
            tick.setObjectName("tick")
            row.addWidget(tick)
            row.addWidget(QLabel(title), 1)
            self.done_list.addWidget(w)
