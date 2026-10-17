"""Colors and the Qt stylesheet, light and dark.

Qt stylesheets are CSS-like rules applied to widgets. objectName works like a
CSS id (#card) and dynamic properties like attribute selectors ([tone="risk"]).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

# Chart series: validated categorical slots (blue, orange) per theme; see recap_page.py.
LIGHT = dict(series_work="#2a78d6", series_game="#eb6834", side="#ecebe6", hover="#e2e0da", bg="#f6f5f2", card="#ffffff", ink="#1d1d1f", muted="#6b6b70", line="#e3e1dc",
             ok="#2f7d4f", ok_bg="#dcefe3", risk="#c92a2a", risk_bg="#fde2e2", accent="#3b5bdb")
DARK = dict(series_work="#3987e5", series_game="#d95926", side="#1b1b1e", hover="#2a2a2f", bg="#151517", card="#1f1f22", ink="#ececee", muted="#9a9aa1", line="#2e2e33",
            ok="#5cc28a", ok_bg="#1f3a2b", risk="#f87171", risk_bg="#4a1f22", accent="#7d93ff")


def colors() -> dict[str, str]:
    dark = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    return DARK if dark else LIGHT


ICON_PATHS = {
    "chevron-down": "M2.5 4.5 6 8l3.5-3.5",
    "chevron-right": "M4.5 2.5 8 6l-3.5 3.5",
    "chevron-left": "M7.5 2.5 4 6l3.5 3.5",
    "check": "M2.6 6.2 5 8.6 9.6 3.6",
}


def icon_path(name: str, color: str, stroke: float = 1.6) -> str:
    """Write a small line icon as an SVG file in the given color and return its path.
    Stylesheets can only load images from files, so icons are generated per theme."""
    path = Path(tempfile.gettempdir()) / f"gameline-{name}-{color.lstrip('#')}-{stroke}.svg"
    if not path.exists():
        path.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
            f'<path d="{ICON_PATHS[name]}" fill="none" stroke="{color}" stroke-width="{stroke}" '
            f'stroke-linecap="round" stroke-linejoin="round"/></svg>'
        )
    return path.as_posix()


def _chevron(color: str) -> str:
    return icon_path("chevron-down", color)


def palette() -> QPalette:
    """Fusion draws popups (calendar, combo lists) from the palette, so match the theme."""
    c = colors()
    pal = QPalette()
    for role, key in (
        (QPalette.ColorRole.Window, "bg"), (QPalette.ColorRole.Base, "card"),
        (QPalette.ColorRole.AlternateBase, "bg"), (QPalette.ColorRole.Button, "card"),
        (QPalette.ColorRole.Text, "ink"), (QPalette.ColorRole.WindowText, "ink"),
        (QPalette.ColorRole.ButtonText, "ink"), (QPalette.ColorRole.Highlight, "accent"),
        (QPalette.ColorRole.PlaceholderText, "muted"), (QPalette.ColorRole.ToolTipBase, "card"),
        (QPalette.ColorRole.ToolTipText, "ink"),
    ):
        pal.setColor(role, QColor(c[key]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    return pal


def dropdown_list_qss() -> str:
    """Styles for a combo box's popup list. Applied to the list itself (see
    styled_combo) because the app-wide sheet doesn't reach into the popup window."""
    c = colors()
    return f"""
    QListView {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 8px;
        padding: 4px; outline: 0; color: {c['ink']}; }}
    QListView::item {{ padding: 0 10px; border-radius: 6px; }}
    QListView::item:hover {{ background: {c['hover']}; }}
    QListView::item:selected {{ background: {c['accent']}; color: white; }}
    """


def stylesheet() -> str:
    c = colors()
    chevron = _chevron(c["muted"])
    check = icon_path("check", "#ffffff", 2.0)
    return f"""
    QWidget {{ color: {c['ink']}; font-size: 14px; }}
    QMainWindow, QDialog, QScrollArea, #page {{ background: {c['bg']}; }}
    QLabel#h1 {{ font-size: 22px; font-weight: 700; }}
    QLabel#h2 {{ color: {c['muted']}; font-size: 12px; font-weight: 600; letter-spacing: 1px; }}
    QLabel[muted="true"] {{ color: {c['muted']}; font-size: 12px; }}
    QLabel#title {{ font-size: 15px; font-weight: 600; }}
    QLabel[pill="ok"] {{ background: {c['ok_bg']}; color: {c['ok']}; border-radius: 10px; padding: 2px 10px; font-weight: 600; }}
    QLabel[pill="risk"] {{ background: {c['risk_bg']}; color: {c['risk']}; border-radius: 10px; padding: 2px 10px; font-weight: 600; }}
    QFrame#card {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 12px; }}
    QProgressBar {{ background: {c['line']}; border: 0; border-radius: 4px; max-height: 8px; }}
    QProgressBar[tone="ok"]::chunk {{ background: {c['ok']}; border-radius: 4px; }}
    QProgressBar[tone="risk"]::chunk {{ background: {c['risk']}; border-radius: 4px; }}
    QPushButton {{ background: {c['accent']}; color: white; border: 0; border-radius: 8px; padding: 7px 14px; font-weight: 600; }}
    QPushButton:disabled {{ background: {c['line']}; color: {c['muted']}; }}
    QPushButton[ghost="true"] {{ background: transparent; color: {c['muted']}; border: 1px solid {c['line']}; padding: 4px 10px; font-weight: 500; }}
    QLineEdit, QPlainTextEdit, QDateTimeEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {c['card']}; border: 1px solid {c['line']}; border-radius: 8px;
        padding: 6px 10px; min-height: 22px; selection-background-color: {c['accent']}; }}
    QLineEdit:focus, QPlainTextEdit:focus, QDateTimeEdit:focus, QSpinBox:focus,
    QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {c['accent']}; }}
    QSpinBox, QDoubleSpinBox {{ padding: 0px; }}
    QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        subcontrol-origin: border; width: 0px; height: 0px; border: 0; }}  /* type or scroll to change */
    QComboBox::drop-down, QDateTimeEdit::drop-down {{
        subcontrol-origin: padding; subcontrol-position: center right; width: 28px; border: 0; }}
    QComboBox::down-arrow, QDateTimeEdit::down-arrow {{ image: url({chevron}); width: 12px; height: 12px; }}
    QComboBox {{ combobox-popup: 0; }}  /* drop the list below the field, not over it */
    QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {c['card']}; border-bottom: 1px solid {c['line']}; }}
    QCalendarWidget QToolButton {{ background: transparent; color: {c['ink']}; font-weight: 600;
        border: 0; border-radius: 6px; padding: 4px 8px; }}
    QCalendarWidget QToolButton:hover {{ background: {c['hover']}; }}
    QCalendarWidget QToolButton::menu-indicator {{ image: none; width: 0; }}
    QCalendarWidget QSpinBox {{ background: {c['card']}; border: 0; padding: 0 4px; min-height: 0; }}
    QCalendarWidget QMenu {{ background: {c['card']}; border: 1px solid {c['line']}; }}
    QCalendarWidget QAbstractItemView {{ background: {c['card']}; color: {c['ink']}; outline: 0;
        selection-background-color: {c['accent']}; selection-color: white; }}
    QCalendarWidget QAbstractItemView:disabled {{ color: {c['muted']}; }}
    QFrame#modal {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 14px; }}
    QPushButton#claudeAccount[tone="ok"] {{ background: {c['ok_bg']}; color: {c['ok']}; }}
    QPushButton#claudeAccount[tone="idle"] {{ background: {c['line']}; color: {c['muted']}; }}
    QPushButton#claudeAccount[tone="idle"]:enabled:hover {{ color: {c['ink']}; }}
    QFrame#toast {{ background: {c['card']}; border: 1px solid {c['line']}; border-left: 3px solid {c['accent']};
                    border-radius: 10px; }}
    QFrame#toast[tone="ok"] {{ border-left-color: {c['ok']}; }}
    QFrame#toast[tone="error"] {{ border-left-color: {c['risk']}; }}
    QLabel[pill="idle"] {{ background: {c['line']}; color: {c['muted']}; border-radius: 10px; padding: 2px 10px; font-weight: 600; }}
    QLabel#dangerTitle {{ color: {c['risk']}; font-size: 12px; font-weight: 600; letter-spacing: 1px; }}
    QPushButton#dangerButton {{ background: transparent; color: {c['risk']}; border: 1px solid {c['risk']}; }}
    QPushButton#dangerButton:hover {{ background: {c['risk_bg']}; }}
    QLabel#warning {{ color: {c['risk']}; font-size: 12px; }}
    QPushButton[danger="true"] {{ background: {c['risk']}; }}
    QLabel#modalTitle {{ font-size: 18px; font-weight: 700; }}
    QFrame#sidebar {{ background: {c['side']}; border-right: 1px solid {c['line']}; }}
    QLabel#brand {{ font-size: 16px; font-weight: 700; padding-left: 4px; }}
    QPushButton#navToggle {{ background: transparent; text-align: left; padding: 0 0 0 12px; border-radius: 8px; }}
    QPushButton#navToggle:hover {{ background: {c['hover']}; }}
    QPushButton#navItem {{ background: transparent; color: {c['muted']}; text-align: left;
                           padding: 9px 0 9px 12px; border-radius: 8px; font-weight: 500; }}
    QPushButton#navItem:hover {{ background: {c['hover']}; color: {c['ink']}; }}
    QPushButton#navItem:checked {{ background: {c['card']}; color: {c['ink']}; font-weight: 600; }}
    QCheckBox {{ spacing: 0px; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px;
        border: 1.5px solid {c['muted']}; background: transparent; }}
    QCheckBox::indicator:hover {{ border-color: {c['accent']}; }}
    QCheckBox::indicator:checked {{ background: {c['ok']}; border-color: {c['ok']}; image: url({check}); }}
    QLabel#task {{ font-size: 14px; }}
    QLabel#task[done="true"] {{ color: {c['muted']}; }}
    QLabel#taskMeta {{ color: {c['muted']}; font-size: 12px; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {c['line']}; border-radius: 3px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['muted']}; }}
    QScrollBar[idle="true"]::handle:vertical {{ background: transparent; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QSpinBox:disabled, QDoubleSpinBox:disabled {{ color: {c['muted']}; background: {c['bg']}; }}
    QPushButton#listToggle {{ background: transparent; color: {c['muted']}; padding: 2px 0; font-weight: 500; text-align: left; }}
    QPushButton#listToggle:hover {{ color: {c['ink']}; }}
    QFrame#gameList {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 8px; }}
    QFrame#gameItem {{ border-radius: 6px; }}
    QFrame#gameItem:hover {{ background: {c['bg']}; }}
    QToolButton#removeGame {{ background: transparent; border: 0; color: {c['muted']}; padding: 2px 6px; border-radius: 4px; }}
    QToolButton#removeGame:hover {{ color: {c['risk']}; background: {c['risk_bg']}; }}
    QPushButton#complete {{ background: transparent; color: {c['muted']}; border: 1px solid {c['line']};
        padding: 4px 10px; font-weight: 500; }}
    QPushButton#complete:hover {{ color: {c['ok']}; border-color: {c['ok']}; }}
    QPushButton#complete[ready="true"] {{ background: {c['ok']}; color: white; border-color: {c['ok']}; font-weight: 600; }}
    QFrame#card[completed="true"] {{ background: {c['bg']}; }}
    QCheckBox#viewToggle {{ spacing: 8px; color: {c['muted']}; }}
    QLabel#stat {{ font-size: 26px; font-weight: 700; }}
    QLabel#tick {{ color: {c['ok']}; font-weight: 700; }}
    QFrame#segment {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 9px; }}
    QPushButton#segButton {{ background: transparent; color: {c['muted']}; padding: 5px 16px; border-radius: 7px; font-weight: 500; }}
    QPushButton#segButton:checked {{ background: {c['accent']}; color: white; font-weight: 600; }}
    QPushButton#foldAll {{ background: transparent; color: {c['muted']}; border: 1px solid {c['line']};
        padding: 0 12px; font-weight: 500; }}
    QPushButton#foldAll:hover {{ color: {c['ink']}; background: {c['hover']}; }}
    QLabel#bigTick {{ color: {c['ok']}; font-size: 40px; font-weight: 700; }}
    QLabel#welcomeTitle {{ font-size: 24px; font-weight: 700; }}
    QLabel#dot {{ background: {c['line']}; border-radius: 4px; }}
    QLabel#dot[current="true"] {{ background: {c['accent']}; }}
    QLabel#stop {{ color: {c['muted']}; font-size: 13px; }}
    QLabel#stop[current="true"] {{ color: {c['ink']}; font-weight: 600; }}
    QSlider#stepSlider {{ min-height: 28px; }}
    QSlider#stepSlider::groove:horizontal {{ height: 6px; background: {c['line']}; border-radius: 3px; }}
    QSlider#stepSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 3px; }}
    /* Apple-style pill knob: wider than tall, sized to fit inside the slider's height. */
    QSlider#stepSlider::handle:horizontal {{ background: #ffffff; border: 1px solid {c['line']};
        width: 34px; height: 20px; margin: -7px 0; border-radius: 10px; }}
    QSlider#stepSlider::handle:horizontal:hover {{ border-color: {c['accent']}; }}
    QPushButton#linkButton {{ background: transparent; color: {c['muted']}; font-weight: 500; padding: 4px 8px; }}
    QPushButton#linkButton:hover {{ color: {c['ink']}; }}
    QPushButton#secondary {{ background: transparent; color: {c['accent']}; border: 1px solid {c['accent']}; }}
    QPushButton#secondary:hover {{ background: {c['hover']}; }}
    QScrollArea#proposalList, QWidget#proposalList {{ background: transparent; }}
    QFrame#proposal {{ border-radius: 8px; }}
    QFrame#proposal:hover {{ background: {c['bg']}; }}
    QToolTip {{ background: {c['card']}; color: {c['ink']}; border: 1px solid {c['line']}; padding: 8px; border-radius: 6px; }}
    QToolButton#collapse {{ background: transparent; border: 0; border-radius: 6px; padding: 4px; }}
    QToolButton#collapse:hover {{ background: {c['line']}; }}
    """
