# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fancy Butler
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).resolve().parent.parent / "resources" / "icons"

BG = "#0f1013"
PANEL = "#16181d"
CARD = "#1c1f26"
LINE = "#2a2e37"
TEXT = "#e7e9ee"
MUTED = "#8b919e"
ACCENT = "#5ee3a1"      # Push "playing" green
ACCENT_2 = "#3d9bff"    # root blue
GOOD = "#3ddc84"
WARN = "#ffcc4d"
BAD = "#ff5c5c"


def icon(name: str, color: str = TEXT, size: int = 20) -> QIcon:
    svg = (ICON_DIR / f"{name}.svg").read_text().replace("currentColor", color)
    r = QSvgRenderer(QByteArray(svg.encode()))
    ic = QIcon()
    for scale in (1, 2):
        pm = QPixmap(QSize(size * scale, size * scale))
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        r.render(p)
        p.end()
        pm.setDevicePixelRatio(scale)
        ic.addPixmap(pm)
    return ic


QSS = f"""
* {{ font-family: "Inter", "Noto Sans", "Cantarell", sans-serif; font-size: 13px; color: {TEXT}; }}
QMainWindow, QWidget#root {{ background: {BG}; }}
QWidget#sidebar {{ background: {PANEL}; border-right: 1px solid {LINE}; }}
QToolButton#nav {{
    background: transparent; border: none; border-radius: 10px; padding: 10px 12px;
    text-align: left; color: {MUTED}; font-weight: 500;
}}
QToolButton#nav:hover {{ background: {CARD}; color: {TEXT}; }}
QToolButton#nav:checked {{ background: #123024; color: {ACCENT}; }}
QLabel#brand {{ font-size: 16px; font-weight: 700; letter-spacing: 0.3px; }}
QLabel#brandSub {{ color: {MUTED}; font-size: 11px; }}
QLabel#h1 {{ font-size: 20px; font-weight: 700; }}
QLabel#muted, QLabel.muted {{ color: {MUTED}; }}
QFrame#card {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 14px; }}
QLabel#pill {{ border-radius: 11px; padding: 3px 10px; font-weight: 600; font-size: 12px; }}
QPushButton {{
    background: {CARD}; border: 1px solid {LINE}; border-radius: 9px; padding: 7px 14px; font-weight: 500;
}}
QPushButton:hover {{ border-color: #3a404c; background: #222631; }}
QPushButton:pressed {{ background: #1a1d24; }}
QPushButton#primary {{ background: {ACCENT}; color: #04140c; border: none; font-weight: 700; }}
QPushButton#primary:hover {{ background: #7af0b6; }}
QPushButton:checked {{ background: #123024; color: {ACCENT}; border-color: {ACCENT}; }}
QPushButton:disabled {{ color: #555b66; }}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: {PANEL}; border: 1px solid {LINE}; border-radius: 8px; padding: 5px 8px; min-height: 18px;
}}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {{ border-color: #3a404c; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {LINE}; selection-background-color: #123024; }}
QTableView, QTreeView, QListView, QPlainTextEdit {{
    background: {PANEL}; border: 1px solid {LINE}; border-radius: 12px; gridline-color: {LINE};
    selection-background-color: #123024; selection-color: {TEXT}; alternate-background-color: #181a20;
}}
QHeaderView::section {{
    background: {PANEL}; color: {MUTED}; border: none; border-bottom: 1px solid {LINE};
    padding: 7px 8px; font-weight: 600; font-size: 11px; text-transform: uppercase;
}}
QTableView::item {{ padding: 4px 8px; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 34px; height: 18px; image: url({ICON_DIR.as_posix()}/switch-off.svg); }}
QCheckBox::indicator:checked {{ image: url({ICON_DIR.as_posix()}/switch-on.svg); }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ width: 0; border: none; }}
QSlider::groove:horizontal {{ height: 6px; background: {LINE}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }}
QProgressBar {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 6px; height: 12px; text-align: center; font-size: 10px; }}
QProgressBar::chunk {{ background: {ACCENT_2}; border-radius: 5px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {LINE}; border-radius: 4px; min-width: 30px; }}
QScrollArea, QScrollArea > QWidget > QWidget#scrollInner {{ background: transparent; }}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid {LINE}; padding: 6px; border-radius: 6px; }}
QStatusBar {{ background: {PANEL}; color: {MUTED}; border-top: 1px solid {LINE}; }}
"""
