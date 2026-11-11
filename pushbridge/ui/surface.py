# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fancy Butler
"""A live drawing of the Push 1.  It lights exactly like the real one, and it's
also a virtual Push: click pads and buttons, scroll or drag the knobs, drag the
touch strip."""
from __future__ import annotations

import time
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..hw import protocol as P
from . import theme

B = P.BUTTONS
GLYPH_BACK = {P.GLYPH_UP: "↑", P.GLYPH_DOWN: "↓", P.GLYPH_FLAT: "♭", P.GLYPH_DOTS: "…",
              P.GLYPH_BLOCK: "█", P.GLYPH_RIGHT: "▸", P.GLYPH_LEFT: "◂"}

# grid units: x columns, y rows
COL_LEFT, COL_STRIP, COL_PADS, COL_SCENE, COL_R1, COL_R2 = 0.0, 1.25, 2.0, 10.15, 11.2, 12.3
WIDTH_U = 13.4
ROW_ENC, ROW_LCD, ROW_UP, ROW_LOW, ROW_PADS = 0.0, 1.2, 2.55, 3.35, 4.3
HEIGHT_U = ROW_PADS + 8 + 0.1

LEFT_COL = ["Undo", "Delete", "Double", "Quantize", "Fixed Length", "Automation", "Duplicate", "New",
            "Record", "Play"]
RIGHT_PAIRS = [("In", "Out"), ("Up", "Down"), ("Left", "Right"), ("Mute", "Solo"), ("Scales", "User"),
               ("Repeat", "Accent"), ("Octave Down", "Octave Up"), ("Add Effect", "Add Track"),
               ("Note", "Session"), ("Select", "Shift")]
RIGHT_TOP = [("Volume", "Pan & Send"), ("Track", "Clip"), ("Device", "Browse")]
SHORT = {"Fixed Length": "Fixed\nLength", "Automation": "Auto-\nmation", "Octave Down": "Oct ↓",
         "Octave Up": "Oct ↑", "Add Effect": "Add\nEffect", "Add Track": "Add\nTrack", "Pan & Send": "Pan &\nSend",
         "Tap Tempo": "Tap", "Metronome": "Metro", "Up": "▲", "Down": "▼", "Left": "◀", "Right": "▶",
         "Duplicate": "Dupli-\ncate", "Quantize": "Quan-\ntize"}


@dataclass
class Item:
    kind: str           # pad, button, encoder, strip, lcd
    id: int
    rect: QRectF        # in grid units
    label: str = ""


def _layout() -> list[Item]:
    it: list[Item] = []
    # encoders
    it.append(Item("encoder", P.ENC_TEMPO, QRectF(0.05, 0.1, 0.9, 0.9), "Tempo"))
    it.append(Item("encoder", P.ENC_SWING, QRectF(1.0, 0.1, 0.9, 0.9), "Swing"))
    for i, cc in enumerate(P.ENC_TRACK):
        it.append(Item("encoder", cc, QRectF(COL_PADS + i + 0.05, 0.1, 0.9, 0.9), ""))
    it.append(Item("encoder", P.ENC_MASTER, QRectF(COL_SCENE - 0.05, 0.1, 0.9, 0.9), "Master"))
    # LCD
    it.append(Item("lcd", 0, QRectF(COL_PADS, ROW_LCD, 8, 1.2)))
    # left top
    it.append(Item("button", B["Tap Tempo"], QRectF(0.05, ROW_LCD + 0.05, 0.85, 0.5), "Tap Tempo"))
    it.append(Item("button", B["Metronome"], QRectF(0.05, ROW_LCD + 0.65, 0.85, 0.5), "Metronome"))
    # button rows
    for i, cc in enumerate(P.UPPER_ROW):
        it.append(Item("button", cc, QRectF(COL_PADS + i + 0.06, ROW_UP, 0.88, 0.6)))
    for i, cc in enumerate(P.LOWER_ROW):
        it.append(Item("button", cc, QRectF(COL_PADS + i + 0.06, ROW_LOW, 0.88, 0.6)))
    it.append(Item("button", B["Master"], QRectF(COL_SCENE, ROW_UP, 0.8, 0.6), "Master"))
    it.append(Item("button", B["Stop"], QRectF(COL_SCENE, ROW_LOW, 0.8, 0.6), "Stop"))
    # right top block
    for r, (a, b) in enumerate(RIGHT_TOP):
        y = 0.1 + r * 0.72
        it.append(Item("button", B[a], QRectF(COL_R1, y, 1.0, 0.6), a))
        it.append(Item("button", B[b], QRectF(COL_R2, y, 1.0, 0.6), b))
    # left column, strip, pads, scene buttons
    rows_y = [ROW_UP + 0.2] + [ROW_PADS - 0.2 + k * 0.89 for k in range(9)]
    for k, name in enumerate(LEFT_COL):
        y = ROW_UP - 0.05 + k * (8 + ROW_PADS - ROW_UP) / 10
        it.append(Item("button", B[name], QRectF(0.05, y, 0.95, 0.72), name))
    it.append(Item("strip", 0, QRectF(COL_STRIP, ROW_PADS + 0.05, 0.5, 7.9)))
    for i in range(P.PADS):
        x, y = i % 8, i // 8
        it.append(Item("pad", P.PAD_FIRST + i, QRectF(COL_PADS + x + 0.06, ROW_PADS + (7 - y) + 0.06, 0.88, 0.88)))
    # 1/32t at the top, 1/4 at the bottom, as printed on the Push
    for k, (name, cc) in enumerate(reversed(list(P.TIME_DIV.items()))):
        it.append(Item("button", cc, QRectF(COL_SCENE, ROW_PADS + k + 0.2, 0.8, 0.6), name))
    for k, (a, b) in enumerate(RIGHT_PAIRS):
        y = ROW_UP - 0.05 + k * (8 + ROW_PADS - ROW_UP) / 10
        it.append(Item("button", B[a], QRectF(COL_R1, y, 1.0, 0.72), a))
        it.append(Item("button", B[b], QRectF(COL_R2, y, 1.0, 0.72), b))
    del rows_y
    return it


ITEMS = _layout()


class Surface(QWidget):
    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.core = core
        self.setMinimumSize(560, 400)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(False)
        self._held_pad = None
        self._held_btn = None
        self._drag_enc = None
        self._drag_y = 0.0
        self._strip = False
        self.mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(33)

    def _tick(self):
        if self.isVisible():
            self.update()

    # ------------------------------------------------------------ geometry
    def _geom(self):
        u = min(self.width() / (WIDTH_U + 0.6), self.height() / (HEIGHT_U + 0.6))
        ox = (self.width() - WIDTH_U * u) / 2
        oy = (self.height() - HEIGHT_U * u) / 2
        return u, ox, oy

    def _r(self, r: QRectF) -> QRectF:
        u, ox, oy = self._geom()
        return QRectF(ox + r.x() * u, oy + r.y() * u, r.width() * u, r.height() * u)

    def _hit(self, pos) -> Item | None:
        for it in ITEMS:
            if self._r(it.rect).contains(pos):
                return it
        return None

    # ------------------------------------------------------------ input
    def _send(self, kind, id_, value):
        self.core.engine.handle(P.Event(kind, id_, value))

    def mousePressEvent(self, e):
        it = self._hit(e.position())
        if not it:
            return
        if it.kind == "pad":
            r = self._r(it.rect)
            # higher up the pad = harder hit
            vel = int(40 + 87 * (1 - (e.position().y() - r.top()) / max(1, r.height())))
            self._held_pad = it.id
            self._send("pad", it.id, max(1, min(127, vel)))
        elif it.kind == "button":
            self._held_btn = it.id
            self._send("button", it.id, 127)
        elif it.kind == "encoder":
            self._drag_enc = it.id
            self._drag_y = e.position().y()
            self._send("enc_touch", it.id, 127)
        elif it.kind == "strip":
            self._strip = True
            self._send("strip_touch", P.STRIP_TOUCH, 127)
            self._strip_to(e.position())

    def mouseMoveEvent(self, e):
        if self._drag_enc is not None:
            dy = self._drag_y - e.position().y()
            steps = int(dy / 4)
            if steps:
                self._drag_y -= steps * 4
                self._send("encoder", self._drag_enc, max(-63, min(63, steps)))
        elif self._strip:
            self._strip_to(e.position())
        elif self._held_pad is not None:
            it = self._hit(e.position())
            if it and it.kind == "pad" and it.id != self._held_pad:   # glide across pads
                self._send("pad_off", self._held_pad, 0)
                self._held_pad = it.id
                self._send("pad", it.id, 100)

    def mouseReleaseEvent(self, _e):
        if self._held_pad is not None:
            self._send("pad_off", self._held_pad, 0)
            self._held_pad = None
        if self._held_btn is not None:
            self._send("button", self._held_btn, 0)
            self._held_btn = None
        if self._drag_enc is not None:
            self._send("enc_touch", self._drag_enc, 0)
            self._drag_enc = None
        if self._strip:
            self._strip = False
            self._send("strip_touch", P.STRIP_TOUCH, 0)

    def wheelEvent(self, e):
        it = self._hit(e.position())
        if it and it.kind == "encoder":
            steps = round(e.angleDelta().y() / 120) or (1 if e.angleDelta().y() > 0 else -1)
            self._send("encoder", it.id, max(-63, min(63, steps)))

    def _strip_to(self, pos):
        r = self._r(next(i for i in ITEMS if i.kind == "strip").rect)
        f = 1 - (pos.y() - r.top()) / max(1, r.height())
        self._send("strip", 0, int(max(0, min(16383, f * 16383))))

    # ------------------------------------------------------------ painting
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        u, ox, oy = self._geom()
        body = QRectF(ox - u * 0.25, oy - u * 0.25, WIDTH_U * u + u * 0.5, HEIGHT_U * u + u * 0.5)
        g = QLinearGradient(body.topLeft(), body.bottomLeft())
        g.setColorAt(0, QColor("#1d1f25"))
        g.setColorAt(1, QColor("#121317"))
        p.setPen(QPen(QColor(theme.LINE), 1))
        p.setBrush(g)
        p.drawRoundedRect(body, u * 0.3, u * 0.3)
        dev = self.core.device
        eng = self.core.engine
        f = QFont(self.font())
        for it in ITEMS:
            r = self._r(it.rect)
            if it.kind == "pad":
                self._pad(p, r, dev.pad_rgb[it.id - P.PAD_FIRST], it.id - P.PAD_FIRST in eng.held, u)
            elif it.kind == "button":
                self._button(p, r, it, dev, u, f)
            elif it.kind == "encoder":
                self._encoder(p, r, it, eng, u, f)
            elif it.kind == "strip":
                self._strip_paint(p, r, eng, u)
            elif it.kind == "lcd":
                self._lcd(p, r, dev, u)
        p.end()

    def _pad(self, p, r, rgb, held, u):
        c = QColor(*rgb)
        lit = sum(rgb) > 20
        base = QColor("#2a2d35")
        p.setPen(QPen(QColor("#f2f4f8") if held else QColor("#30333b"), 1.5 if held else 1))
        if lit:
            gl = QColor(c)
            gl.setAlphaF(0.25)
            p.setBrush(gl)
            p.drawRoundedRect(r.adjusted(-u * 0.04, -u * 0.04, u * 0.04, u * 0.04), u * 0.14, u * 0.14)
            p.setBrush(c)
        else:
            p.setBrush(base)
        p.drawRoundedRect(r, u * 0.1, u * 0.1)

    def _btn_color(self, cc: int, dev) -> QColor | None:
        v = dev.button.get(cc, 0)
        if cc in P.LOWER_ROW:
            rgb = dev.row_rgb[P.LOWER_ROW.index(cc)]
            return QColor(*rgb) if sum(rgb) > 20 else None
        if cc in P.TWO_COLOUR:
            rgb = P.rg_rgb(v)
            return QColor(*rgb) if sum(rgb) > 0 else None
        if v <= 0:
            return None
        bright = v >= 4
        if cc == B["Play"]:
            return QColor(60, 230, 90) if bright else QColor(30, 90, 40)
        if cc == B["Record"]:
            return QColor(255, 60, 50) if bright else QColor(100, 30, 25)
        return QColor("#f4efe2") if bright else QColor("#6b6860")

    def _button(self, p, r, it, dev, u, f):
        col = self._btn_color(it.id, dev)
        pressed = self._held_btn == it.id
        p.setPen(QPen(QColor("#f2f4f8") if pressed else QColor("#30333b"), 1))
        p.setBrush(QColor("#25282f"))
        p.drawRoundedRect(r, u * 0.08, u * 0.08)
        txt = SHORT.get(it.label, it.label)
        if col is not None and (it.id in P.LOWER_ROW or it.id in P.UPPER_ROW or it.id in P.TIME_DIV.values()):
            # coloured strip LEDs
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(r.adjusted(u * 0.08, r.height() * 0.62, -u * 0.08, -r.height() * 0.12), 2, 2)
            col = QColor("#cfd3db")
        f.setPixelSize(max(7, int(u * (0.16 if "\n" in txt else 0.18))))
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(col if col is not None else QColor("#5d626d"))
        p.drawText(r, Qt.AlignCenter, txt)

    def _encoder(self, p, r, it, eng, u, f):
        c = r.center()
        rad = min(r.width(), r.height()) * 0.38
        touched = it.id in eng.enc_touch
        p.setPen(QPen(QColor(theme.ACCENT) if touched else QColor("#3a3e48"), 1.5))
        p.setBrush(QColor("#2a2d35"))
        p.drawEllipse(c, rad, rad)
        val = None
        if it.id in P.ENC_TRACK:
            val = eng.s["encoder_values"][it.id - P.ENC_TRACK[0]] / 127
        elif it.id == P.ENC_MASTER:
            val = eng.s["encoder_values"][8] / 127
        elif it.id == P.ENC_TEMPO:
            val = (float(eng.s["tempo"]) - 20) / 280
        if val is not None and not eng.s["encoder_relative"] or it.id == P.ENC_TEMPO:
            path = QPainterPath()
            ar = QRectF(c.x() - rad - 3, c.y() - rad - 3, 2 * rad + 6, 2 * rad + 6)
            path.arcMoveTo(ar, 225)
            path.arcTo(ar, 225, -270 * max(0.0, min(1.0, val or 0)))
            p.setPen(QPen(QColor(theme.ACCENT), max(2, u * 0.05), Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        if it.label:
            f.setPixelSize(max(7, int(u * 0.15)))
            p.setFont(f)
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(r.left() - 10, r.bottom() - u * 0.08, r.width() + 20, u * 0.2), Qt.AlignCenter, it.label)

    def _strip_paint(self, p, r, eng, u):
        p.setPen(QPen(QColor("#30333b"), 1))
        p.setBrush(QColor("#1a1c21"))
        p.drawRoundedRect(r, u * 0.12, u * 0.12)
        frac = eng.strip_value / 16383
        y = r.bottom() - frac * r.height()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.ACCENT))
        if eng.s["strip"] == "pitch":
            mid = r.center().y()
            p.drawRoundedRect(QRectF(r.left() + 3, min(y, mid), r.width() - 6, max(2, abs(y - mid))), 2, 2)
        elif eng.s["strip"] == "mod":
            p.drawRoundedRect(QRectF(r.left() + 3, y, r.width() - 6, r.bottom() - y - 3), 2, 2)

    def _lcd(self, p, r, dev, u):
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor("#0b1a22"))
        g.setColorAt(1, QColor("#08131a"))
        p.setPen(QPen(QColor("#253540"), 1))
        p.setBrush(g)
        p.drawRoundedRect(r, u * 0.06, u * 0.06)
        f = QFont(self.mono)
        inner = r.adjusted(u * 0.08, u * 0.08, -u * 0.08, -u * 0.08)
        lh = inner.height() / 4
        f.setPixelSize(max(6, int(lh * 0.78)))
        p.setFont(f)
        # stretch the 68 columns to the panel width
        cw = inner.width() / P.LCD_WIDTH
        p.setPen(QColor("#9fe7ff") if dev.connected or self.core.demo else QColor("#4d6b78"))
        for line, text in enumerate(dev.lcd):
            y = inner.top() + line * lh
            for col, ch in enumerate(text[:P.LCD_WIDTH]):
                if ch == " ":
                    continue
                if ord(ch) < 32:
                    ch = GLYPH_BACK.get(ord(ch), "?")
                if ch == "█":
                    p.fillRect(QRectF(inner.left() + col * cw + 0.5, y + lh * 0.15, cw - 1, lh * 0.7), QColor("#9fe7ff"))
                    continue
                p.drawText(QRectF(inner.left() + col * cw, y, cw * 1.6, lh), Qt.AlignLeft | Qt.AlignVCenter, ch)
