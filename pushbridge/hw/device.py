# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fancy Butler
"""The Push itself: finds it, keeps a mirror of every LED and the LCD, and only
sends what changed.  The mirror is also what the on-screen surface draws."""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from . import protocol as P


class PushDevice:
    def __init__(self, seq=None):
        self.seq = seq                     # alsa.Seq, or None for demo / no ALSA
        self.connected = False
        self.ports: list = []
        self.name = ""
        self.identity = ""
        self.full_rgb = True
        self.brightness = 1.0
        # mirrors
        self.pad_rgb: list[tuple[int, int, int]] = [(0, 0, 0)] * P.PADS
        self.row_rgb: list[tuple[int, int, int]] = [(0, 0, 0)] * 8
        self.button: dict[int, int] = {}
        self.lcd: list[str] = [" " * P.LCD_WIDTH] * P.LCD_LINES
        self._lcd_sent: list[Optional[list[int]]] = [None] * P.LCD_LINES
        self._lock = threading.RLock()
        self.on_event: Optional[Callable[[P.Event], None]] = None
        self.on_status: Optional[Callable[[str, str], None]] = None
        self.last_rx = 0.0
        self.last_tx = 0.0
        self.muted = False                 # True while Ableton Live (or another app) owns the Push

    # ------------------------------------------------------------ discovery
    def scan(self) -> bool:
        """Look for a Push 1 and hook it up.  Returns True if the state changed."""
        if self.seq is None:
            return False
        from .alsa import is_push1
        found = [p for p in self.seq.ports() if is_push1(p.client_name) and p.client != self.seq.client]
        if found and not self.connected:
            self.ports = found
            self.name = found[0].client_name
            self.seq.connect_push(found)
            self.connected = True
            self._lcd_sent = [None] * P.LCD_LINES
            if not self.muted:
                self.init_hardware()
            self._status("connected", f"{self.name} ({', '.join(p.name for p in found)})")
            return True
        if not found and self.connected:
            self.connected = False
            self.ports = []
            self._status("waiting", "Push unplugged")
            return True
        if not found and not self.connected and not self.ports:
            self._status("waiting", "Plug in the Push and switch it on")
        return False

    def init_hardware(self):
        self._send(P.mode_live())
        self._send(P.aftertouch_mode(True))
        self._send(P.IDENTITY_REQUEST)
        self.repaint()

    def _status(self, state: str, detail: str):
        if (state, detail) == getattr(self, "_last_status", None):
            return
        self._last_status = (state, detail)
        if self.on_status:
            self.on_status(state, detail)

    # ------------------------------------------------------------ in
    def handle_raw(self, msg: bytes, _port: int = 0):
        self.last_rx = time.time()
        ev = P.parse(msg)
        if ev is None:
            return
        if ev.kind == "sysex":
            if len(msg) > 5 and msg[1] == 0x7E and msg[3] == 0x06 and msg[4] == 0x02:
                self.identity = " ".join(f"{b:02X}" for b in msg[5:-1])
            return
        if self.on_event:
            self.on_event(ev)

    # ------------------------------------------------------------ out
    def _send(self, msg: bytes):
        if self.seq is not None and self.connected and not self.muted:
            self.last_tx = time.time()
            self.seq.to_push(msg)

    def _dim(self, rgb):
        b = self.brightness
        return tuple(int(c * b) for c in rgb)

    def set_pad(self, i: int, rgb: tuple[int, int, int], force: bool = False):
        with self._lock:
            if not force and self.pad_rgb[i] == rgb:
                return
            self.pad_rgb[i] = rgb
            self._paint_rgb(P.PAD_FIRST + i, i, rgb, note=True)

    def set_row(self, i: int, rgb: tuple[int, int, int], force: bool = False):
        with self._lock:
            if not force and self.row_rgb[i] == rgb:
                return
            self.row_rgb[i] = rgb
            self._paint_rgb(P.LOWER_ROW[i], 64 + i, rgb, note=False)

    def _paint_rgb(self, addr: int, index: int, rgb, note: bool):
        rgb = self._dim(rgb)
        vel = P.palette_index(*rgb)
        # palette first: always works; full RGB on top when enabled
        self._send(bytes((0x90 if note else 0xB0, addr, vel)))
        if self.full_rgb and vel:
            self._send(P.rgb_led(index, *rgb))

    def set_button(self, cc: int, value: int, force: bool = False):
        with self._lock:
            if not force and self.button.get(cc) == value:
                return
            self.button[cc] = value
            self._send(bytes((0xB0, cc, value)))

    def set_lcd(self, line: int, text: str):
        with self._lock:
            text = (text + " " * P.LCD_WIDTH)[:P.LCD_WIDTH]
            self.lcd[line] = text

    def flush_lcd(self):
        """Send LCD lines that changed (called at ~25 Hz)."""
        with self._lock:
            for i, text in enumerate(self.lcd):
                b = P.lcd_bytes(text)
                if b != self._lcd_sent[i]:
                    self._lcd_sent[i] = b
                    self._send(P.lcd_line(i, text))

    def repaint(self):
        with self._lock:
            for i, c in enumerate(self.pad_rgb):
                self._paint_rgb(P.PAD_FIRST + i, i, c, note=True)
            for i, c in enumerate(self.row_rgb):
                self._paint_rgb(P.LOWER_ROW[i], 64 + i, c, note=False)
            for cc, v in self.button.items():
                self._send(bytes((0xB0, cc, v)))
            self._lcd_sent = [None] * P.LCD_LINES
            self.flush_lcd()

    def blank(self):
        """Everything off and a goodbye on the LCD (on quit)."""
        with self._lock:
            for i in range(P.PADS):
                self.set_pad(i, (0, 0, 0))
            for i in range(8):
                self.set_row(i, (0, 0, 0))
            for cc in list(self.button):
                self.set_button(cc, 0)
            for i in range(P.LCD_LINES):
                self.set_lcd(i, "")
            self.set_lcd(1, P.cells("", "", "", "Push Bridge", "", "is closed"))
            self.flush_lcd()

    def send_raw(self, msg: bytes):
        """Pass-through mode: an app talks to the Push directly."""
        self._send(msg)
