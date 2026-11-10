# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fancy Butler
"""Wires Push <-> engine <-> apps.  Usable with or without the GUI."""
from __future__ import annotations

import threading
import time
from typing import Callable

from .engine import settings as S
from .engine.engine import Engine
from .hw import alsa
from .hw import protocol as P
from .hw.device import PushDevice


class Core:
    def __init__(self, demo: bool = False):
        self.demo = demo
        self.settings = S.load()
        self.status = ("starting", "")
        self.status_listeners: list[Callable[[str, str], None]] = []
        self.seq = None
        self.midi_error = ""
        if not demo:
            if not alsa.seq_available():
                self.midi_error = "ALSA sequencer (/dev/snd/seq) not available"
            else:
                try:
                    self.seq = alsa.Seq()
                except Exception as e:  # noqa: BLE001
                    self.midi_error = str(e)
        self.device = PushDevice(self.seq)
        self.device.full_rgb = bool(self.settings["full_rgb"])
        self.device.brightness = max(0.1, int(self.settings["brightness"]) / 100)
        self.last_out = 0.0
        self.engine = Engine(self.settings, self.device, self._to_apps)
        self.engine.on_midi_out = self._ping_out
        self.device.on_event = self.engine.handle
        self.device.on_status = self._on_status
        if self.seq:
            self.seq.on_push = self.device.handle_raw
            self.seq.on_app = self.engine.handle_app
            self.seq.on_change = self._rescan_soon
        self._stop = threading.Event()
        self._rescan = threading.Event()
        self._dirty_save = 0.0

    def _to_apps(self, msg: bytes):
        if self.seq:
            self.seq.to_apps(msg)

    def _ping_out(self):
        self.last_out = time.time()

    # ------------------------------------------------------------ lifecycle
    def start(self):
        self.engine.refresh()
        threading.Thread(target=self._watch, name="pushbridge-watch", daemon=True).start()
        threading.Thread(target=self._ticker, name="pushbridge-tick", daemon=True).start()
        if self.demo:
            self._on_status("connected", "Demo: no hardware, click the surface")
        elif self.midi_error:
            self._on_status("error", self.midi_error)

    def stop(self):
        self._stop.set()
        try:
            self.engine.all_notes_off()
            if self.engine.playing:
                self.engine.set_playing(False)
            if self.device.connected:
                self.device.blank()
        except Exception:
            pass
        self.save()
        if self.seq:
            time.sleep(0.05)
            self.seq.close()

    # ------------------------------------------------------------ Ableton Live hand-off
    def set_handoff(self, on: bool, reason: str = "manual"):
        """Give the Push to Ableton Live (or anything else that drives it directly),
        or take it back.  While handed off we send nothing to the Push."""
        if on == self.engine.standby:
            return
        with self.engine.lock:
            if on:
                self.engine.all_notes_off()
                if self.engine.playing:
                    self.engine.set_playing(False)
                if self.engine.passthrough:
                    self.engine.passthrough = False
                self.engine.standby = True
                self.device.muted = True
            else:
                self.engine.standby = False
                self.device.muted = False
                self._handoff_reason = ""
                if self.device.connected:
                    self.device.init_hardware()
                self.engine.refresh()
        self._handoff_reason = reason if on else ""
        self._on_status(*self.status)
        self.engine._changed()

    def other_drivers(self) -> list[str]:
        """Apps (other than us and PipeWire's listener) connected straight to the Push."""
        if not (self.seq and self.device.connected):
            return []
        from .health import parse_seq_clients
        clients = parse_seq_clients(alsa.connections_text())
        names = set()
        for p in self.device.ports:
            info = clients.get(p.client, {}).get("ports", {}).get(p.port)
            if not info:
                continue
            # only apps that *send to* the Push can fight us; listeners are harmless
            for c, _ in info["from"]:
                if c in (self.seq.client, 0):
                    continue
                n = clients.get(c, {}).get("name", str(c))
                if "pipewire" not in n.lower() and "through" not in n.lower():
                    names.add(n)
        return sorted(names)

    def _auto_handoff(self):
        if not self.settings.get("auto_handoff", True):
            return
        others = self.other_drivers()
        if others and not self.engine.standby:
            self.set_handoff(True, "auto:" + ", ".join(others))
        elif not others and self.engine.standby and getattr(self, "_handoff_reason", "").startswith("auto:"):
            self.set_handoff(False)

    def _rescan_soon(self):
        self._rescan.set()

    def _watch(self):
        """Hot-plug: rescan when ALSA announces a change, and every 2 s anyway."""
        while not self._stop.is_set():
            if self.seq:
                try:
                    if self.device.scan() and self.device.connected:
                        self.engine.refresh()
                    self._auto_handoff()
                except Exception as e:  # noqa: BLE001
                    self._on_status("error", f"Scan failed: {e}")
            self._rescan.wait(2.0)
            self._rescan.clear()
            time.sleep(0.15)        # let a newly plugged Push finish registering its ports
            if self._dirty_save and time.time() - self._dirty_save > 1.0:
                self.save()

    def _ticker(self):
        next_lcd = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            try:
                self.engine.tick(now)
                if now >= next_lcd:
                    next_lcd = now + 0.04
                    self.device.flush_lcd()
            except Exception:
                import traceback
                traceback.print_exc()
            time.sleep(0.001)

    def _on_status(self, state: str, detail: str):
        self.status = (state, detail)
        for cb in list(self.status_listeners):
            cb(state, detail)

    # ------------------------------------------------------------ settings
    def changed(self, repaint: bool = True):
        """The UI changed a setting."""
        self.device.full_rgb = bool(self.settings["full_rgb"])
        self.device.brightness = max(0.1, int(self.settings["brightness"]) / 100)
        if repaint:
            self.engine.refresh()
        self._dirty_save = time.time()

    def repaint_hardware(self):
        self.device.repaint()

    def save(self):
        self._dirty_save = 0.0
        try:
            S.save(self.settings)
        except OSError:
            pass

    def test_leds(self):
        """A quick rainbow across the pads, then back to normal."""
        def run():
            import colorsys
            for step in range(48):
                for i in range(P.PADS):
                    x, y = i % 8, i // 8
                    r, g, b = colorsys.hsv_to_rgb(((x + y) / 16 + step / 24) % 1, 1, 1)
                    self.device.set_pad(i, (int(r * 255), int(g * 255), int(b * 255)))
                time.sleep(0.03)
            self.engine.refresh()
        threading.Thread(target=run, daemon=True).start()
