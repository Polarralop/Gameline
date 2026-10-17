"""Colors and the Qt stylesheet, light and dark.

Qt stylesheets are CSS-like rules applied to widgets. objectName works like a
CSS id (#card) and dynamic properties like attribute selectors ([tone="risk"]).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

LIGHT = dict(side="#ecebe6", hover="#e2e0da", bg="#f6f5f2", card="#ffffff", ink="#1d1d1f", muted="#6b6b70", line="#e3e1dc",
             ok="#2f7d4f", ok_bg="#dcefe3", risk="#c2410c", risk_bg="#fbe3d6", accent="#3b5bdb")
DARK = dict(side="#1b1b1e", hover="#2a2a2f", bg="#151517", card="#1f1f22", ink="#ececee", muted="#9a9aa1", line="#2e2e33",
            ok="#5cc28a", ok_bg="#1f3a2b", risk="#fb8b4f", risk_bg="#43271a", accent="#7d93ff")


def colors() -> dict[str, str]:
    dark = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    return DARK if dark else LIGHT


def stylesheet() -> str:
    c = colors()
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
        background: {c['card']}; border: 1px solid {c['line']}; border-radius: 8px; padding: 5px 8px; }}
    QFrame#sidebar {{ background: {c['side']}; border-right: 1px solid {c['line']}; }}
    QLabel#brand {{ font-size: 16px; font-weight: 700; padding-left: 4px; }}
    QPushButton#navToggle {{ background: transparent; color: {c['muted']}; font-size: 18px; padding: 4px 10px; }}
    QPushButton#navToggle:hover {{ background: {c['hover']}; }}
    QPushButton#navItem {{ background: transparent; color: {c['muted']}; text-align: left;
                           padding: 9px 12px; border-radius: 8px; font-weight: 500; }}
    QPushButton#navItem:hover {{ background: {c['hover']}; color: {c['ink']}; }}
    QPushButton#navItem:checked {{ background: {c['card']}; color: {c['ink']}; font-weight: 600; }}
    QCheckBox[done="true"] {{ color: {c['muted']}; }}
    """
