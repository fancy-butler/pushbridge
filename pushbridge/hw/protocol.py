# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fancy Butler
"""Ableton Push (1st generation) MIDI protocol.

Ableton never published this for Push 1; everything here comes from
hardware-tested community work:
  * crosslandwa/push-wrapper (button CCs, encoders, touch notes, LCD and RGB sysex)
  * Carlborg/hardpush (mode / aftertouch sysex, two-colour LED values, LCD glyphs)
  * pushmod.blogspot.com (RGB pad sysex, pads 0-71 incl. the lower button row)
  * Adam Murray's palette notes (velocity -> colour table)
"""
from __future__ import annotations

import colorsys
from dataclasses import dataclass
from typing import Optional

SYSEX_HEAD = (0xF0, 0x47, 0x7F, 0x15)      # Akai manufacturer id, Push 1 device id

# ------------------------------------------------------------------ pads
PAD_FIRST = 36                              # bottom-left pad; rows of 8 going up
PADS = 64


def pad_note(x: int, y: int) -> int:
    """(x, y) with (0, 0) bottom-left -> the note the pad sends."""
    return PAD_FIRST + y * 8 + x


def pad_xy(note: int) -> Optional[tuple[int, int]]:
    i = note - PAD_FIRST
    if 0 <= i < PADS:
        return i % 8, i // 8
    return None


# ------------------------------------------------------------------ encoders / touch
ENC_TRACK = list(range(71, 79))             # the 8 encoders above the display
ENC_MASTER = 79
ENC_TEMPO = 14
ENC_SWING = 15
ENCODERS = [ENC_TEMPO, ENC_SWING] + ENC_TRACK + [ENC_MASTER]
# touch notes: encoders 0-7, master 8, swing 9, tempo 10; touch strip 12
TOUCH_NOTE = {**{i: 71 + i for i in range(8)}, 8: ENC_MASTER, 9: ENC_SWING, 10: ENC_TEMPO}
STRIP_TOUCH = 12


def rel(value: int) -> int:
    """Encoder CC value (two's complement, accelerates when turned fast) -> delta."""
    return value if value < 64 else value - 128


# ------------------------------------------------------------------ buttons
BUTTONS = {
    "Tap Tempo": 3, "Metronome": 9, "Undo": 119, "Delete": 118, "Double": 117, "Quantize": 116,
    "Fixed Length": 90, "Automation": 89, "Duplicate": 88, "New": 87, "Record": 86, "Play": 85,
    "Master": 28, "Stop": 29, "Left": 44, "Right": 45, "Up": 46, "Down": 47,
    "Volume": 114, "Pan & Send": 115, "Track": 112, "Clip": 113, "Device": 110, "Browse": 111,
    "In": 62, "Out": 63, "Mute": 60, "Solo": 61, "Scales": 58, "User": 59, "Repeat": 56, "Accent": 57,
    "Octave Down": 54, "Octave Up": 55, "Add Effect": 52, "Add Track": 53, "Note": 50, "Session": 51,
    "Select": 48, "Shift": 49,
}
CC_NAME = {v: k for k, v in BUTTONS.items()}
TIME_DIV = {"1/4": 36, "1/4t": 37, "1/8": 38, "1/8t": 39, "1/16": 40, "1/16t": 41, "1/32": 42, "1/32t": 43}
TIME_DIV_BEATS = {36: 1.0, 37: 2 / 3, 38: 0.5, 39: 1 / 3, 40: 0.25, 41: 1 / 6, 42: 0.125, 43: 1 / 12}
for _n, _c in TIME_DIV.items():
    CC_NAME[_c] = _n
UPPER_ROW = list(range(20, 28))             # just under the display: red/orange/yellow/green LEDs
LOWER_ROW = list(range(102, 110))           # above the pads: RGB, same palette as the pads
for _i, _c in enumerate(UPPER_ROW):
    CC_NAME[_c] = f"Upper {_i + 1}"
for _i, _c in enumerate(LOWER_ROW):
    CC_NAME[_c] = f"Lower {_i + 1}"
ALL_BUTTON_CCS = sorted(set(BUTTONS.values()) | set(TIME_DIV.values()) | set(UPPER_ROW) | set(LOWER_ROW))
TWO_COLOUR = set(UPPER_ROW) | set(TIME_DIV.values())

# single-colour buttons
OFF, DIM, DIM_BLINK, DIM_FAST, ON, ON_BLINK, ON_FAST = 0, 1, 2, 3, 4, 5, 6
# two-colour (red/green) buttons: dim value per colour; +3 = bright, +1/+2 = blink / fast blink
RG_DIM = {"red": 1, "orange": 7, "yellow": 13, "green": 19}


def rg(colour: str, bright: bool = True) -> int:
    return RG_DIM[colour] + (3 if bright else 0)


# ------------------------------------------------------------------ sysex
def sysex(*data: int) -> bytes:
    return bytes(SYSEX_HEAD + tuple(d & 0x7F for d in data) + (0xF7,))


def mode_live() -> bytes:
    """Put Push in its default ('Live') mode; we play the part of Live."""
    return sysex(0x62, 0, 1, 0)


def aftertouch_mode(poly: bool = True) -> bytes:
    return sysex(0x5C, 0, 1, 0 if poly else 1)


IDENTITY_REQUEST = bytes((0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7))


def rgb_led(index: int, r: int, g: int, b: int) -> bytes:
    """Full colour for pad 0-63 (bottom-left first) or lower-row button 64-71."""
    v = []
    for c in (r, g, b):
        c = max(0, min(255, int(c)))
        v += [c >> 4, c & 0x0F]
    return sysex(0x04, 0, 0x08, index, 0, *v)


# ------------------------------------------------------------------ LCD
LCD_LINES = 4
LCD_WIDTH = 68
CELL_OFFSETS = [0, 9, 17, 26, 34, 43, 51, 60]    # one cell above each encoder
CELL_WIDTHS = [9, 8, 9, 8, 9, 8, 9, 8]

# The Push LCD has a few custom glyphs below ASCII 32.
GLYPH_UP, GLYPH_DOWN, GLYPH_FLAT, GLYPH_DOTS, GLYPH_BLOCK, GLYPH_RIGHT, GLYPH_LEFT = 0, 1, 27, 28, 29, 30, 31
GLYPH_FOLDER = 7
TO_GLYPH = {"↑": GLYPH_UP, "↓": GLYPH_DOWN, "♭": GLYPH_FLAT, "…": GLYPH_DOTS, "█": GLYPH_BLOCK,
            "→": GLYPH_RIGHT, "←": GLYPH_LEFT, "▸": GLYPH_RIGHT, "◂": GLYPH_LEFT}
_ASCII = {"♯": "#", "·": "-", "—": "-", "–": "-", "≈": "~", "♮": "n", "é": "e", "ü": "u", "ö": "o",
          "ā": "a", "×": "x", "’": "'", "‘": "'", "“": '"', "”": '"'}


def lcd_bytes(text: str) -> list[int]:
    """Unicode text -> exactly 68 LCD character codes."""
    out = []
    for ch in text:
        if ch in TO_GLYPH:
            out.append(TO_GLYPH[ch])
            continue
        ch = _ASCII.get(ch, ch)
        o = ord(ch[0])
        out.append(o if 32 <= o < 127 else ord("?"))
    out = out[:LCD_WIDTH]
    return out + [32] * (LCD_WIDTH - len(out))


def lcd_line(line: int, text: str) -> bytes:
    """Line 0 is the top line (closest to the encoders)."""
    return sysex(0x18 + line, 0, 69, 0, *lcd_bytes(text))


def cells(*items: str) -> str:
    """Lay out up to 8 strings, one under each encoder."""
    s = [" "] * LCD_WIDTH
    for i, t in enumerate(items[:8]):
        t = (t or "")[:CELL_WIDTHS[i] - (1 if i % 2 == 0 else 0)]
        for j, ch in enumerate(t):
            s[CELL_OFFSETS[i] + j] = ch
    return "".join(s)


def bar(fraction: float, width: int = 8) -> str:
    n = round(max(0.0, min(1.0, fraction)) * width)
    return "█" * n + " " * (width - n)


# ------------------------------------------------------------------ palette
# Velocity palette for pads / lower row (used when full-RGB is off).
# 0 off, 1 dark grey, 2 grey, 3 white, then 14 hues x 4 shades
# (pastel, bright, medium, dim) starting at red; 60 = bright orange.
_HUES = ["red", "amber", "yellow", "lime", "green", "spring", "turquoise", "cyan", "sky", "ocean",
         "blue", "orchid", "magenta", "pink"]


def palette_index(r: int, g: int, b: int) -> int:
    """Nearest palette velocity for an RGB colour."""
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    if l < 0.04:
        return 0
    if s < 0.18:
        return 3 if l > 0.6 else (2 if l > 0.3 else 1)
    hue_i = int(round(h * 14)) % 14
    base = 4 + hue_i * 4
    if l > 0.75:
        return base                 # pastel
    if l > 0.38:
        return base + 1             # bright
    if l > 0.2:
        return base + 2             # medium
    return base + 3                 # dim


# ------------------------------------------------------------------ incoming
@dataclass
class Event:
    kind: str          # pad, pad_off, pressure, button, encoder, enc_touch, strip, strip_touch, sysex
    id: int = 0        # pad note / cc / encoder cc
    value: int = 0     # velocity, pressure, 127/0 for buttons, delta for encoders, 14-bit bend
    raw: bytes = b""


def parse(msg: bytes) -> Optional[Event]:
    if not msg:
        return None
    if msg[0] == 0xF0:
        return Event("sysex", raw=bytes(msg))
    if len(msg) < 3:
        return None
    st, d1, d2 = msg[0] & 0xF0, msg[1], msg[2]
    if st == 0x90 and d2 == 0:
        st = 0x80
    if st in (0x90, 0x80):
        if PAD_FIRST <= d1 < PAD_FIRST + PADS:
            return Event("pad" if st == 0x90 else "pad_off", d1, d2 if st == 0x90 else 0)
        if d1 == STRIP_TOUCH:
            return Event("strip_touch", d1, 127 if st == 0x90 else 0)
        if d1 in TOUCH_NOTE:
            return Event("enc_touch", TOUCH_NOTE[d1], 127 if st == 0x90 else 0)
        return None
    if st == 0xA0 and PAD_FIRST <= d1 < PAD_FIRST + PADS:
        return Event("pressure", d1, d2)
    if st == 0xB0:
        if d1 in ENCODERS:
            return Event("encoder", d1, rel(d2))
        return Event("button", d1, 127 if d2 else 0)
    if st == 0xE0:
        return Event("strip", 0, (d2 << 7) | d1)
    return None


def palette_rgb(index: int) -> tuple[int, int, int]:
    """Rough on-screen colour for a palette velocity (for the surface mirror)."""
    if index <= 0:
        return (0, 0, 0)
    if index <= 3:
        return [(40, 40, 40), (110, 110, 110), (230, 230, 230)][index - 1]
    if index == 60:
        return (255, 120, 0)
    if index > 60:
        return (160, 160, 160)
    hue_i, shade = divmod(index - 4, 4)
    light = [0.78, 0.5, 0.32, 0.16][shade]
    r, g, b = colorsys.hls_to_rgb(hue_i / 14, light, 1.0)
    return int(r * 255), int(g * 255), int(b * 255)


def rg_rgb(value: int) -> tuple[int, int, int]:
    """On-screen colour for a two-colour button value."""
    if value <= 0:
        return (0, 0, 0)
    if value > 24:
        return (40, 220, 60)
    group, step = divmod(value - 1, 6)
    base = [(255, 40, 30), (255, 130, 20), (220, 230, 40), (40, 220, 60)][min(group, 3)]
    f = 1.0 if step >= 3 else 0.35
    return tuple(int(c * f) for c in base)
