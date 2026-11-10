# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fancy Butler
"""What the Push does when you touch it.  Pure logic: the device mirror goes
in, MIDI for apps comes out, so it's fully testable without hardware."""
from __future__ import annotations

import math
import threading
import time
from typing import Callable, Optional

from .. import theory as T
from ..hw import protocol as P

ROOT_UPPER = [0, 7, 2, 9, 4, 11]        # C G D A E B   (top row under the display)
ROOT_LOWER = [5, 10, 3, 8, 1, 6]        # F Bb Eb Ab Db Gb (row above the pads)
LAYOUTS = ["4ths", "3rds", "seq"]
LAYOUT_LABEL = {"4ths": "4ths", "3rds": "3rds", "seq": "Sequent"}
ROW_DEGREES = {"4ths": 3, "3rds": 2, "seq": 8}
ROW_SEMIS = {"4ths": 5, "3rds": 4, "seq": 8}
DRUM_QUAD = [(255, 120, 20), (230, 220, 40), (30, 200, 230), (190, 70, 255)]
OWN = {P.BUTTONS[n] for n in ("Shift", "Scales", "Octave Up", "Octave Down", "Note", "Accent", "Repeat",
                              "Play", "Tap Tempo", "User", "Up", "Down", "Left", "Right")} | set(P.TIME_DIV.values())


def _scale_dim(rgb, f):
    return tuple(int(c * f) for c in rgb)


class Engine:
    def __init__(self, settings: dict, device, out: Callable[[bytes], None]):
        self.s = settings
        self.dev = device
        self.out = out
        self.lock = threading.RLock()
        self.shift = False
        self.overlay: Optional[str] = None        # None | "scales"
        self.passthrough = False
        self.standby = False                      # Live has the Push: hands off
        self.accent = False
        self.repeat = False
        self.playing = False
        self.held: dict[int, int] = {}            # pad -> note it played
        self.held_vel: dict[int, int] = {}
        self.pressure: dict[int, int] = {}
        self.note_count: dict[int, int] = {}
        self.feedback: set[int] = set()
        self.enc_touch: set[int] = set()
        self._enc_frac = [0.0] * 9
        self._chanpress = 0
        self._taps: list[float] = []
        self._repeat_next: dict[int, float] = {}
        self._clock_next = 0.0
        self._beat_tick = 0
        self._last_beat_led = None
        self.strip_value = 8192
        self.last_activity = time.time()
        self.on_change: Optional[Callable[[], None]] = None   # UI refresh hint
        self.on_midi_out: Optional[Callable[[], None]] = None

    # ================================================================ helpers
    @property
    def scale(self) -> T.Scale:
        return T.SCALES[T.scale_index(self.s["scale"])]

    @property
    def channel(self) -> int:
        return int(self.s["channel"]) & 0x0F

    def _send(self, *b: int):
        self.out(bytes(b))
        if self.on_midi_out:
            self.on_midi_out()

    def _changed(self):
        if self.on_change:
            self.on_change()

    def base_note(self) -> int:
        return 36 + int(self.s["root"]) + 12 * int(self.s["octave"])

    def pad_to_note(self, i: int) -> Optional[int]:
        x, y = i % 8, i // 8
        if self.s["mode"] == "drums":
            q = (y // 4) * 2 + (x // 4)
            n = int(self.s["drum_base"]) + q * 16 + (y % 4) * 4 + (x % 4)
        else:
            lay = self.s["layout"]
            base = self.base_note()
            if self.s["in_key"]:
                steps = self.scale.steps
                deg = x + y * ROW_DEGREES.get(lay, 3)
                n = base + 12 * (deg // len(steps)) + steps[deg % len(steps)]
            else:
                n = base + x + y * ROW_SEMIS.get(lay, 5)
        return n if 0 <= n <= 127 else None

    def octave_range(self) -> tuple[bool, bool]:
        """Can we go (down, up)?"""
        if self.s["mode"] == "drums":
            b = int(self.s["drum_base"])
            return b - 16 >= 0, b + 16 + 63 <= 127
        o = int(self.s["octave"])
        lo = 36 + int(self.s["root"]) + 12 * (o - 1)
        return lo >= 0, lo + 24 <= 127 - 12

    def velocity(self, v: int) -> int:
        if self.accent:
            return 127
        curve = self.s["velocity_curve"]
        if curve == "fixed":
            return max(1, min(127, int(self.s["fixed_velocity"])))
        g = {"soft": 0.6, "hard": 1.6}.get(curve, 1.0)
        return max(1, min(127, round(127 * math.pow(v / 127, g))))

    # ================================================================ pads
    def pad_color(self, i: int) -> tuple[int, int, int]:
        c = self.s["colors"]
        n = self.pad_to_note(i)
        if n is None:
            return (0, 0, 0)
        if self.note_count.get(n):
            return tuple(c["pressed"])
        if n in self.feedback:
            return tuple(c["feedback"])
        if self.s["mode"] == "drums":
            x, y = i % 8, i // 8
            return _scale_dim(DRUM_QUAD[(y // 4) * 2 + (x // 4)], 0.45)
        rel = (n - int(self.s["root"])) % 12
        if rel == 0:
            return tuple(c["root"])
        if rel in self.scale.steps:
            return tuple(c["scale"])
        return tuple(c["out"])

    def paint_pads(self):
        for i in range(P.PADS):
            self.dev.set_pad(i, self.pad_color(i))

    def _note_on(self, n: int, vel: int):
        cnt = self.note_count.get(n, 0)
        self.note_count[n] = cnt + 1
        if cnt == 0:
            self._send(0x90 | self.channel, n, vel)

    def _note_off(self, n: int):
        cnt = self.note_count.get(n, 0)
        if cnt <= 1:
            self.note_count.pop(n, None)
            if cnt:
                self._send(0x80 | self.channel, n, 0)
        else:
            self.note_count[n] = cnt - 1

    def pad_press(self, i: int, vel: int):
        n = self.pad_to_note(i)
        if n is None or i in self.held:
            return
        v = self.velocity(vel)
        self.held[i] = n
        self.held_vel[i] = v
        self._note_on(n, v)
        if self.repeat:
            self._repeat_next[i] = time.monotonic() + self.repeat_period()
        self.paint_pads()

    def pad_release(self, i: int):
        n = self.held.pop(i, None)
        self.held_vel.pop(i, None)
        self.pressure.pop(i, None)
        self._repeat_next.pop(i, None)
        if n is None:
            return
        self._note_off(n)
        self._update_chanpress()
        self.paint_pads()

    def pad_pressure(self, i: int, p: int):
        if i not in self.held:
            return
        self.pressure[i] = p
        mode = self.s["aftertouch"]
        if mode == "poly":
            self._send(0xA0 | self.channel, self.held[i], p)
        elif mode == "channel":
            self._update_chanpress()

    def _update_chanpress(self):
        if self.s["aftertouch"] != "channel":
            return
        p = max(self.pressure.values(), default=0)
        if p != self._chanpress:
            self._chanpress = p
            self._send(0xD0 | self.channel, p)

    def all_notes_off(self):
        for n in list(self.note_count):
            self._send(0x80 | self.channel, n, 0)
        self.note_count.clear()
        self.held.clear()
        self.held_vel.clear()
        self.pressure.clear()
        self._repeat_next.clear()

    # ================================================================ events
    def handle(self, ev: P.Event):
        with self.lock:
            if self.standby:
                return
            self.last_activity = time.time()
            if self.passthrough and not (ev.kind == "button" and ev.id == P.BUTTONS["User"]):
                self._passthrough_in(ev)
                return
            k = ev.kind
            if k == "pad":
                self.pad_press(ev.id - P.PAD_FIRST, ev.value)
            elif k == "pad_off":
                self.pad_release(ev.id - P.PAD_FIRST)
            elif k == "pressure":
                self.pad_pressure(ev.id - P.PAD_FIRST, ev.value)
            elif k == "button":
                self.button(ev.id, ev.value > 0)
            elif k == "encoder":
                self.encoder(ev.id, ev.value)
            elif k == "enc_touch":
                (self.enc_touch.add if ev.value else self.enc_touch.discard)(ev.id)
                self.render_lcd()
            elif k == "strip":
                self.strip(ev.value)
            elif k == "strip_touch" and not ev.value and self.s["strip"] == "pitch":
                self.strip(8192)
            self._changed()

    def _passthrough_in(self, ev: P.Event):
        """User mode: the Push becomes a plain MIDI controller for your DAW."""
        if ev.raw:
            return
        k = ev.kind
        if k in ("pad", "pad_off"):
            self._send(0x90 if k == "pad" else 0x80, ev.id, ev.value)
        elif k == "pressure":
            self._send(0xA0, ev.id, ev.value)
        elif k == "button":
            self._send(0xB0, ev.id, ev.value)
        elif k == "encoder":
            self._send(0xB0, ev.id, ev.value & 0x7F)
        elif k == "enc_touch":
            note = {v: k2 for k2, v in P.TOUCH_NOTE.items()}[ev.id]
            self._send(0x90 if ev.value else 0x80, note, ev.value)
        elif k == "strip":
            self._send(0xE0, ev.value & 0x7F, ev.value >> 7)
        elif k == "strip_touch":
            self._send(0x90 if ev.value else 0x80, P.STRIP_TOUCH, ev.value)

    def strip(self, v: int):
        self.strip_value = v
        mode = self.s["strip"]
        if mode == "pitch":
            self._send(0xE0 | self.channel, v & 0x7F, v >> 7)
        elif mode == "mod":
            self._send(0xB0 | self.channel, 1, v >> 7)

    # ---------------------------------------------------------------- encoders
    def encoder(self, cc: int, delta: int):
        if cc in (P.ENC_TEMPO, P.ENC_SWING):
            step = 1.0 if cc == P.ENC_TEMPO and not self.shift else 0.1
            self.set_tempo(float(self.s["tempo"]) + delta * step)
            return
        idx = 8 if cc == P.ENC_MASTER else cc - P.ENC_TRACK[0]
        if self.overlay == "scales":
            self._enc_frac[idx] += delta / 2
            steps = int(self._enc_frac[idx])
            if steps:
                self._enc_frac[idx] -= steps
                cur = T.scale_index(self.s["scale"])
                self.s["scale"] = T.SCALES[(cur + steps) % len(T.SCALES)].name
                self.refresh()
            return
        enc = self.s["encoders"][idx]
        ch = self.channel
        if self.s["encoder_relative"]:
            self._send(0xB0 | ch, int(enc["cc"]) & 0x7F, delta & 0x7F)
            return
        if self.shift:
            self._enc_frac[idx] += delta / 4
            delta = int(self._enc_frac[idx])
            self._enc_frac[idx] -= delta
        vals = self.s["encoder_values"]
        nv = max(0, min(127, vals[idx] + delta))
        if nv != vals[idx]:
            vals[idx] = nv
            self._send(0xB0 | ch, int(enc["cc"]) & 0x7F, nv)
            self.render_lcd()

    def set_tempo(self, bpm: float):
        self.s["tempo"] = round(max(20.0, min(300.0, bpm)), 1)
        self.render_lcd()
        self._changed()

    # ---------------------------------------------------------------- buttons
    def button(self, cc: int, down: bool):
        B = P.BUTTONS
        if cc == B["Shift"]:
            self.shift = down
            self.dev.set_button(cc, P.ON if down else P.DIM)
            return
        if cc not in OWN and not (self.overlay == "scales" and (cc in P.UPPER_ROW or cc in P.LOWER_ROW)):
            # not ours: hand it to the app as a CC (MIDI-learnable)
            self._send(0xB0 | (int(self.s["button_channel"]) & 0x0F), cc, 127 if down else 0)
            return
        if not down:
            if cc in (B["Octave Up"], B["Octave Down"], B["Up"], B["Down"], B["Left"], B["Right"]):
                self.paint_buttons()
            return
        if cc == B["User"]:
            self.set_passthrough(not self.passthrough)
        elif cc == B["Scales"]:
            self.overlay = None if self.overlay == "scales" else "scales"
            self.refresh()
        elif cc in (B["Octave Up"], B["Octave Down"], B["Up"], B["Down"]):
            self.shift_octave(1 if cc in (B["Octave Up"], B["Up"]) else -1)
            self.dev.set_button(cc, P.ON)
        elif cc in (B["Left"], B["Right"]):
            self.nudge(1 if cc == B["Right"] else -1)
            self.dev.set_button(cc, P.ON)
        elif cc == B["Note"]:
            self.all_notes_off()
            self.s["mode"] = "drums" if self.s["mode"] == "notes" else "notes"
            self.refresh()
        elif cc == B["Accent"]:
            self.accent = not self.accent
            self.paint_buttons()
        elif cc == B["Repeat"]:
            self.repeat = not self.repeat
            self._repeat_next = {i: time.monotonic() for i in self.held} if self.repeat else {}
            self.paint_buttons()
        elif cc in P.TIME_DIV_BEATS:
            self.s["repeat_div"] = cc
            self.paint_buttons()
        elif cc == B["Play"]:
            self.set_playing(not self.playing)
        elif cc == B["Tap Tempo"]:
            self.tap()
        elif self.overlay == "scales":
            self._scales_button(cc)
        self.render_lcd()

    def _scales_button(self, cc: int):
        if cc in P.UPPER_ROW[:6]:
            self.set_root(ROOT_UPPER[P.UPPER_ROW.index(cc)])
        elif cc in P.LOWER_ROW[:6]:
            self.set_root(ROOT_LOWER[P.LOWER_ROW.index(cc)])
        elif cc == P.UPPER_ROW[6]:
            lay = self.s["layout"]
            self.s["layout"] = LAYOUTS[(LAYOUTS.index(lay) + 1) % len(LAYOUTS)] if lay in LAYOUTS else "4ths"
            self.refresh()
        elif cc == P.UPPER_ROW[7]:
            self.s["in_key"] = not self.s["in_key"]
            self.refresh()
        elif cc == P.LOWER_ROW[6]:
            self.s["middle_c"] = 4 if int(self.s["middle_c"]) == 3 else 3
            self.refresh()

    def set_root(self, root: int):
        self.s["root"] = root % 12
        self.refresh()

    def shift_octave(self, d: int):
        down_ok, up_ok = self.octave_range()
        if (d < 0 and not down_ok) or (d > 0 and not up_ok):
            return
        if self.s["mode"] == "drums":
            self.s["drum_base"] = int(self.s["drum_base"]) + 16 * d
        else:
            self.s["octave"] = int(self.s["octave"]) + d
        self.refresh()

    def nudge(self, d: int):
        """Left/Right: move the root a semitone (shift: a 5th) without leaving the scale."""
        self.set_root(int(self.s["root"]) + (7 * d if self.shift else d))

    def set_passthrough(self, on: bool):
        self.all_notes_off()
        self.passthrough = on
        if on:
            for i in range(P.PADS):
                self.dev.set_pad(i, (0, 0, 0))
            for i in range(8):
                self.dev.set_row(i, (0, 0, 0))
            for cc in P.ALL_BUTTON_CCS:
                self.dev.set_button(cc, 0)
            self.dev.set_button(P.BUTTONS["User"], P.ON)
            for i in range(4):
                self.dev.set_lcd(i, "")
            self.dev.set_lcd(1, "User mode: Push is a plain MIDI controller for your software.")
            self.dev.set_lcd(2, "Press User again to come back.")
        else:
            self.refresh()
        self._changed()

    # ---------------------------------------------------------------- clock
    def set_playing(self, on: bool):
        self.playing = on
        if self.s["clock"] != "off":
            self._send(0xFA if on else 0xFC)
        self._clock_next = time.monotonic()
        self._beat_tick = 0
        self.paint_buttons()
        self.render_lcd()
        self._changed()

    def tap(self):
        now = time.monotonic()
        self._taps = [t for t in self._taps if now - t < 2.0][-4:] + [now]
        if len(self._taps) >= 2:
            iv = [b - a for a, b in zip(self._taps, self._taps[1:])]
            self.set_tempo(60.0 / (sum(iv) / len(iv)))

    def repeat_period(self) -> float:
        return 60.0 / float(self.s["tempo"]) * P.TIME_DIV_BEATS.get(int(self.s["repeat_div"]), 0.25)

    def tick(self, now: float):
        """Called ~every millisecond from the ticker thread."""
        with self.lock:
            if self.standby:
                return
            clock = self.s["clock"]
            if clock == "always" or (clock == "playing" and self.playing):
                if now >= self._clock_next:
                    period = 60.0 / float(self.s["tempo"]) / 24
                    if now - self._clock_next > 0.25:
                        self._clock_next = now
                    self._send(0xF8)
                    self._clock_next += period
                    self._beat_tick = (self._beat_tick + 1) % 24
            elif now >= self._clock_next:
                self._clock_next = now + 60.0 / float(self.s["tempo"]) / 24
                self._beat_tick = (self._beat_tick + 1) % 24
            if not self.passthrough:
                beat = self._beat_tick < 4
                if beat != self._last_beat_led:
                    self._last_beat_led = beat
                    self.dev.set_button(P.BUTTONS["Tap Tempo"], P.ON if beat else P.DIM)
                if self.repeat and self._repeat_next:
                    period = self.repeat_period()
                    for i, t in list(self._repeat_next.items()):
                        if now >= t and i in self.held:
                            n = self.held[i]
                            v = self.pressure.get(i) or self.held_vel.get(i, 100)
                            v = 127 if self.accent else max(1, v)
                            self._send(0x80 | self.channel, n, 0)
                            self._send(0x90 | self.channel, n, v)
                            self._repeat_next[i] = max(t + period, now - period)

    # ================================================================ from apps
    def handle_app(self, msg: bytes):
        with self.lock:
            if self.standby:
                return
            if self.passthrough:
                self.dev.send_raw(msg)
                self._mirror_raw(msg)
                return
            if len(msg) < 3:
                return
            st, d1, d2 = msg[0] & 0xF0, msg[1], msg[2]
            ch = msg[0] & 0x0F
            if ch == self.channel and st in (0x90, 0x80):
                if st == 0x90 and d2:
                    self.feedback.add(d1)
                else:
                    self.feedback.discard(d1)
                self.paint_pads()
                self._changed()
            elif st == 0xB0 and ch == (int(self.s["button_channel"]) & 0x0F) and d1 not in OWN:
                if d1 in P.LOWER_ROW:
                    self.dev.set_row(P.LOWER_ROW.index(d1), P.palette_rgb(d2))
                elif d1 in P.ALL_BUTTON_CCS:
                    self.dev.set_button(d1, d2)
                self._changed()

    def _mirror_raw(self, msg: bytes):
        """Keep the on-screen surface in step while an app drives the Push."""
        if msg and msg[0] == 0xF0:
            if len(msg) >= 16 and bytes(msg[:4]) == bytes(P.SYSEX_HEAD) and msg[4] == 0x04:
                idx = msg[7]
                rgb = tuple((msg[9 + 2 * k] << 4) | msg[10 + 2 * k] for k in range(3))
                with self.dev._lock:
                    if idx < 64:
                        self.dev.pad_rgb[idx] = rgb
                    elif idx < 72:
                        self.dev.row_rgb[idx - 64] = rgb
            elif len(msg) >= 9 and bytes(msg[:4]) == bytes(P.SYSEX_HEAD) and 0x18 <= msg[4] <= 0x1B:
                line, off = msg[4] - 0x18, msg[7]
                chars = "".join(chr(c) if c >= 32 else " " for c in msg[8:-1])
                cur = self.dev.lcd[line]
                self.dev.lcd[line] = (cur[:off] + chars + cur[off + len(chars):])[:P.LCD_WIDTH]
            return
        if len(msg) < 3:
            return
        st, d1, d2 = msg[0] & 0xF0, msg[1], msg[2]
        with self.dev._lock:
            if st in (0x90, 0x80) and P.pad_xy(d1):
                self.dev.pad_rgb[d1 - P.PAD_FIRST] = P.palette_rgb(d2 if st == 0x90 else 0)
            elif st == 0xB0 and d1 in P.LOWER_ROW:
                self.dev.row_rgb[P.LOWER_ROW.index(d1)] = P.palette_rgb(d2)
            elif st == 0xB0:
                self.dev.button[d1] = d2
        self._changed()

    # ================================================================ painting
    def refresh(self):
        with self.lock:
            if self.passthrough or self.standby:
                return
            self.paint_pads()
            self.paint_buttons()
            self.render_lcd()
            self._changed()

    def paint_buttons(self):
        B = P.BUTTONS
        d = self.dev
        for cc in P.ALL_BUTTON_CCS:
            if cc not in OWN and cc not in P.UPPER_ROW and cc not in P.LOWER_ROW and cc not in d.button:
                d.set_button(cc, P.DIM)             # free for your software: dim = "does something"
        d.set_button(B["Shift"], P.ON if self.shift else P.DIM)
        d.set_button(B["Scales"], P.ON if self.overlay == "scales" else P.DIM)
        d.set_button(B["User"], P.ON if self.passthrough else P.DIM)
        d.set_button(B["Note"], P.ON if self.s["mode"] == "notes" else P.DIM)
        d.set_button(B["Accent"], P.ON if self.accent else P.DIM)
        d.set_button(B["Repeat"], P.ON if self.repeat else P.DIM)
        d.set_button(B["Play"], P.ON if self.playing else P.DIM)
        down_ok, up_ok = self.octave_range()
        for name, ok in (("Octave Down", down_ok), ("Down", down_ok), ("Octave Up", up_ok), ("Up", up_ok)):
            d.set_button(B[name], P.DIM if ok else P.OFF)
        d.set_button(B["Left"], P.DIM)
        d.set_button(B["Right"], P.DIM)
        for cc in P.TIME_DIV.values():
            sel = cc == int(self.s["repeat_div"])
            d.set_button(cc, P.rg("green", True) if sel else (P.rg("orange", False) if self.repeat else P.rg("yellow", False)))
        if self.overlay == "scales":
            root = int(self.s["root"])
            for i, cc in enumerate(P.UPPER_ROW[:6]):
                d.set_button(cc, P.rg("green", True) if ROOT_UPPER[i] == root else P.rg("orange", False))
            d.set_button(P.UPPER_ROW[6], P.rg("yellow", True))
            d.set_button(P.UPPER_ROW[7], P.rg("green", True) if self.s["in_key"] else P.rg("red", True))
            for i in range(6):
                d.set_row(i, tuple(self.s["colors"]["root"]) if ROOT_LOWER[i] == root else (60, 60, 70))
            d.set_row(6, (200, 200, 200))
            d.set_row(7, (0, 0, 0))
        else:
            for cc in P.UPPER_ROW:
                if d.button.get(cc) in (None, P.rg("green", True), P.rg("yellow", True), P.rg("red", True)):
                    d.set_button(cc, P.rg("orange", False))
            for i in range(8):
                if d.row_rgb[i] in ((0, 0, 0), (60, 60, 70), (200, 200, 200), tuple(self.s["colors"]["root"])):
                    d.set_row(i, (25, 25, 30))

    def render_lcd(self):
        if self.passthrough:
            return
        s = self.s
        d = self.dev
        mc = int(s["middle_c"])
        root = int(s["root"])
        rname = T.pc_name(root, root, self.scale).replace("b", "♭")
        if self.overlay == "scales":
            idx = T.scale_index(s["scale"])
            sc = T.SCALES[idx]
            head = f"{rname} {sc.name}{'' if s['in_key'] else ' (chromatic)'}"
            d.set_lcd(0, f"{head:<54}{'knob: ' + str(idx + 1) + '/' + str(len(T.SCALES)):>14}")
            d.set_lcd(1, sc.group + (f" - aka {sc.aka}" if sc.aka else ""))
            low = [("▸" if ROOT_LOWER[i] == root else "↓") + T.FLAT[ROOT_LOWER[i]].replace("b", "♭") for i in range(6)]
            d.set_lcd(2, P.cells(*low, f"↓C{mc}=mid", ""))
            up = [("▸" if ROOT_UPPER[i] == root else " ") + T.SHARP[ROOT_UPPER[i]] for i in range(6)]
            d.set_lcd(3, P.cells(*up, LAYOUT_LABEL.get(s["layout"], "4ths"), "In Key" if s["in_key"] else "Chromat."))
            return
        names = [e["name"][:8] for e in s["encoders"][:8]]
        vals = s["encoder_values"]
        if s["encoder_relative"]:
            d.set_lcd(0, P.cells(*names))
            d.set_lcd(1, P.cells(*["  ←  →" for _ in range(8)]))
        else:
            d.set_lcd(0, P.cells(*[("▸" + n if (P.ENC_TRACK[i] in self.enc_touch) else n) for i, n in enumerate(names)]))
            d.set_lcd(1, P.cells(*[P.bar(v / 127, 3) + f"{v:4d}" for v in vals[:8]]))
        play = "▸" if self.playing else " "
        tempo = f"{play}{float(s['tempo']):.1f} BPM"
        if s["mode"] == "drums":
            b = int(s["drum_base"])
            d.set_lcd(2, f"Drums {T.note_name(b, mc)}-{T.note_name(b + 63, mc)}  Ch {self.channel + 1}"
                         f"{'  Accent' if self.accent else ''}{'  Repeat' if self.repeat else ''}   {tempo}")
        else:
            lay = LAYOUT_LABEL.get(s["layout"], "4ths") + (" In Key" if s["in_key"] else " Chromatic")
            d.set_lcd(2, f"{rname} {self.scale.name}  {lay}  {T.note_name(self.base_note(), mc)}"
                         f"  Ch {self.channel + 1}{'  Acc' if self.accent else ''}{'  Rpt' if self.repeat else ''}"
                         f"  {tempo}")
        held = sorted(set(self.held.values()))
        if held:
            sc = self.scale
            chord = T.name_chord(held, mc, root, sc) or ""
            text = chord + "   " + " ".join(T.note_name(n, mc, root, sc) for n in held)
            d.set_lcd(3, text.replace("b", "♭") if s["mode"] == "notes"
                      else " ".join(T.note_name(n, mc) for n in held))
        else:
            d.set_lcd(3, "Scales: key & scale   Note: drums   User: plain MIDI")
