# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fancy Butler
from __future__ import annotations

import time

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox,
                               QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
                               QPushButton, QScrollArea, QSlider, QSpinBox, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from .. import __version__, health
from .. import theory as T
from ..engine.engine import LAYOUT_LABEL, LAYOUTS
from . import theme
from .surface import Surface
from ..platform_util import IS_WIN
from .tray import Tray, autostart_enabled, set_autostart


class Events(QObject):
    """Thread-safe hop from MIDI threads into the GUI thread."""
    changed = Signal()
    status = Signal(str, str)


def card(title: str = "", subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(10)
    if title:
        t = QLabel(title)
        t.setStyleSheet("font-weight:700; font-size:14px;")
        lay.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("muted")
        s.setWordWrap(True)
        lay.addWidget(s)
    return f, lay


def page_header(title: str, sub: str = "") -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 6)
    lay.setSpacing(2)
    t = QLabel(title)
    t.setObjectName("h1")
    lay.addWidget(t)
    if sub:
        s = QLabel(sub)
        s.setObjectName("muted")
        s.setWordWrap(True)
        lay.addWidget(s)
    return w


def row(label: str, widget: QWidget, hint: str = "") -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    l = QLabel(label)
    l.setMinimumWidth(170)
    if hint:
        l.setToolTip(hint)
        widget.setToolTip(hint)
    h.addWidget(l)
    h.addWidget(widget, 1)
    return w


def scroll(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    inner.setObjectName("scrollInner")
    sa.setWidget(inner)
    return sa


ROOT_NAMES = ["C", "C♯ / D♭", "D", "D♯ / E♭", "E", "F", "F♯ / G♭", "G", "G♯ / A♭", "A", "A♯ / B♭", "B"]


# ===================================================================== Play page
class PlayPage(QWidget):
    def __init__(self, core):
        super().__init__()
        self.core = core
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)
        top = QHBoxLayout()
        top.addWidget(page_header("Play", ""), 1)
        self.pill = QLabel("Starting…")
        self.pill.setObjectName("pill")
        top.addWidget(self.pill, 0, Qt.AlignTop)
        lay.addLayout(top)

        bar = QFrame()
        bar.setObjectName("card")
        g = QGridLayout(bar)
        g.setContentsMargins(14, 10, 14, 10)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(6)

        self.mode = QButtonGroup(self)
        modes = QHBoxLayout()
        for i, (key, label) in enumerate((("notes", "Notes"), ("drums", "Drums"))):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setProperty("key", key)
            self.mode.addButton(b, i)
            modes.addWidget(b)
        self.mode.idClicked.connect(lambda i: self._set("mode", ("notes", "drums")[i]))

        self.root = QComboBox()
        self.root.addItems(ROOT_NAMES)
        self.root.currentIndexChanged.connect(lambda i: self._set("root", i))

        self.scale = QComboBox()
        self.scale.setMinimumWidth(240)
        self.scale.setMaxVisibleItems(24)
        model = QStandardItemModel(self.scale)
        self._scale_rows = {}
        group = None
        for i, sc in enumerate(T.SCALES):
            if sc.group != group:
                group = sc.group
                hdr = QStandardItem(group.upper())
                hdr.setFlags(Qt.NoItemFlags)
                hdr.setForeground(QColor(theme.MUTED))
                model.appendRow(hdr)
            it = QStandardItem(sc.name)
            it.setData(sc.name, Qt.UserRole)
            if sc.aka:
                it.setToolTip(f"aka {sc.aka}")
            self._scale_rows[sc.name] = model.rowCount()
            model.appendRow(it)
        self.scale.setModel(model)
        self.scale.currentIndexChanged.connect(self._scale_picked)
        self.find = QLineEdit()
        self.find.setPlaceholderText("Find a scale (name or aka)…")
        self.find.setClearButtonEnabled(True)
        self.find.returnPressed.connect(self._find_scale)
        self.find.textEdited.connect(self._find_scale)

        self.layout_cb = QComboBox()
        for k in LAYOUTS:
            self.layout_cb.addItem(LAYOUT_LABEL[k], k)
        self.layout_cb.currentIndexChanged.connect(lambda i: self._set("layout", LAYOUTS[i]))
        self.in_key = QCheckBox("In key")
        self.in_key.toggled.connect(lambda on: self._set("in_key", on))

        octv = QHBoxLayout()
        self.oct_down = QPushButton("Oct −")
        self.oct_up = QPushButton("Oct +")
        self.oct_lbl = QLabel()
        self.oct_lbl.setMinimumWidth(80)
        self.oct_lbl.setAlignment(Qt.AlignCenter)
        self.oct_down.clicked.connect(lambda: self._octave(-1))
        self.oct_up.clicked.connect(lambda: self._octave(1))
        octv.addWidget(self.oct_down)
        octv.addWidget(self.oct_lbl)
        octv.addWidget(self.oct_up)

        self.chan = QSpinBox()
        self.chan.setRange(1, 16)
        self.chan.setPrefix("Ch ")
        self.chan.valueChanged.connect(lambda v: self._set("channel", v - 1))
        self.tempo = QDoubleSpinBox()
        self.tempo.setRange(20, 300)
        self.tempo.setDecimals(1)
        self.tempo.setSuffix(" BPM")
        self.tempo.valueChanged.connect(lambda v: self._set("tempo", round(v, 1), repaint=False))
        self.play = QPushButton(theme.icon("activity", theme.TEXT, 16), "Play")
        self.play.setCheckable(True)
        self.play.toggled.connect(lambda on: self.core.engine.set_playing(on) if on != self.core.engine.playing else None)

        g.addLayout(modes, 0, 0)
        g.addWidget(self.root, 0, 1)
        g.addWidget(self.scale, 0, 2)
        g.addWidget(self.find, 0, 3)
        g.addWidget(self.layout_cb, 0, 4)
        g.addWidget(self.in_key, 0, 5)
        self.handoff = QPushButton(theme.icon("unplug", theme.TEXT, 16), "Hand to Live")
        self.handoff.setCheckable(True)
        self.handoff.setToolTip("Step aside so Ableton Live (or anything that drives the Push directly) has it. "
                                "Push Bridge also does this by itself when Live connects, and takes it back after.")
        self.handoff.toggled.connect(lambda on: None if self._syncing else self.core.set_handoff(on))
        g.addLayout(octv, 1, 0, 1, 2)
        g.addWidget(self.handoff, 1, 5)
        g.addWidget(self.chan, 1, 2)
        g.addWidget(self.tempo, 1, 3)
        g.addWidget(self.play, 1, 4)
        g.setColumnStretch(2, 2)
        g.setColumnStretch(3, 2)
        lay.addWidget(bar)

        self.surface = Surface(core)
        lay.addWidget(self.surface, 1)
        hint = QLabel("Click pads (higher on a pad = harder hit), click buttons, scroll or drag knobs, drag the strip.")
        hint.setObjectName("muted")
        lay.addWidget(hint)
        self._syncing = False
        self.sync()

    def _set(self, key, value, repaint=True):
        if self._syncing:
            return
        if key == "mode":
            self.core.engine.all_notes_off()
        self.core.settings[key] = value
        self.core.changed(repaint)
        self.sync()

    def _octave(self, d):
        self.core.engine.shift_octave(d)
        self.core.changed(False)

    def _scale_picked(self, i):
        name = self.scale.itemData(i, Qt.UserRole)
        if name:
            self._set("scale", name)

    def _find_scale(self, *_):
        hits = T.find_scales(self.find.text()) if self.find.text().strip() else []
        self.find.setStyleSheet("" if hits or not self.find.text() else f"color:{theme.BAD};")
        if hits:
            self.scale.setCurrentIndex(self._scale_rows[T.SCALES[hits[0]].name])

    def sync(self):
        s = self.core.settings
        e = self.core.engine
        self._syncing = True
        try:
            for b in self.mode.buttons():
                b.setChecked(b.property("key") == s["mode"])
            self.root.setCurrentIndex(int(s["root"]))
            self.scale.setCurrentIndex(self._scale_rows.get(s["scale"], 1))
            self.layout_cb.setCurrentIndex(LAYOUTS.index(s["layout"]) if s["layout"] in LAYOUTS else 0)
            self.in_key.setChecked(bool(s["in_key"]))
            notes = s["mode"] == "notes"
            for w in (self.root, self.scale, self.find, self.layout_cb, self.in_key):
                w.setEnabled(notes)
            mc = int(s["middle_c"])
            if notes:
                self.oct_lbl.setText(T.note_name(e.base_note(), mc))
            else:
                b = int(s["drum_base"])
                self.oct_lbl.setText(f"{T.note_name(b, mc)}–{T.note_name(b + 63, mc)}")
            down, up = e.octave_range()
            self.oct_down.setEnabled(down)
            self.oct_up.setEnabled(up)
            self.chan.setValue(int(s["channel"]) + 1)
            if abs(self.tempo.value() - float(s["tempo"])) > 0.05:
                self.tempo.setValue(float(s["tempo"]))
            self.play.setChecked(e.playing)
            self.handoff.setChecked(e.standby)
            self.handoff.setText("Take it back" if e.standby else "Hand to Live")
            self.play.setText("Stop" if e.playing else "Play")
        finally:
            self._syncing = False

    def set_status(self, state, detail):
        txt = {"connected": "Push connected", "waiting": "Waiting for the Push", "error": "Problem",
               "starting": "Starting…"}.get(state, state)
        if self.core.demo:
            txt = "Demo"
        col = {"connected": theme.GOOD, "error": theme.BAD}.get(state, theme.WARN)
        if self.core.engine.passthrough:
            txt, col = "User mode", theme.ACCENT_2
        if self.core.engine.standby:
            who = getattr(self.core, "_handoff_reason", "")
            txt, col = "Handed off", theme.ACCENT_2
            detail = ("Automatically: " + who[5:] + " is driving the Push") if who.startswith("auto:") else \
                "You handed the Push to Live"
        self.pill.setText(txt)
        self.pill.setToolTip(detail)
        self.pill.setStyleSheet(f"background:{col}22; color:{col};")


# ===================================================================== Pads page
class PadsPage(QWidget):
    COLOR_ROLES = [("root", "Root note"), ("scale", "In scale"), ("out", "Out of scale (chromatic)"),
                   ("pressed", "Pressed"), ("feedback", "Notes from your software")]

    def __init__(self, core):
        super().__init__()
        self.core = core
        s = core.settings
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(14)
        lay.addWidget(page_header("Pads & strip", "How hits, pressure and the touch strip turn into MIDI."))

        c, cl = card("Feel")
        self.curve = QComboBox()
        for k, label in (("linear", "Linear"), ("soft", "Soft (light touch = loud)"), ("hard", "Hard (dig in)"),
                         ("fixed", "Fixed velocity")):
            self.curve.addItem(label, k)
        self.curve.setCurrentIndex(max(0, self.curve.findData(s["velocity_curve"])))
        self.curve.currentIndexChanged.connect(lambda i: self._set("velocity_curve", self.curve.itemData(i)))
        cl.addWidget(row("Velocity curve", self.curve))
        self.fixed = QSpinBox()
        self.fixed.setRange(1, 127)
        self.fixed.setValue(int(s["fixed_velocity"]))
        self.fixed.valueChanged.connect(lambda v: self._set("fixed_velocity", v, False))
        cl.addWidget(row("Fixed velocity", self.fixed, "Used when the curve is Fixed. Accent on the Push always sends 127."))
        self.at = QComboBox()
        for k, label in (("poly", "Polyphonic (per pad)"), ("channel", "Channel (strongest pad)"), ("off", "Off")):
            self.at.addItem(label, k)
        self.at.setCurrentIndex(max(0, self.at.findData(s["aftertouch"])))
        self.at.currentIndexChanged.connect(lambda i: self._set("aftertouch", self.at.itemData(i), False))
        cl.addWidget(row("Pressure (aftertouch)", self.at,
                         "Most synths understand Channel; MPE-ish and Bitwig/Surge like Polyphonic."))
        self.strip = QComboBox()
        for k, label in (("pitch", "Pitch bend (springs back)"), ("mod", "Mod wheel, CC 1 (stays put)"), ("off", "Off")):
            self.strip.addItem(label, k)
        self.strip.setCurrentIndex(max(0, self.strip.findData(s["strip"])))
        self.strip.currentIndexChanged.connect(lambda i: self._set("strip", self.strip.itemData(i), False))
        cl.addWidget(row("Touch strip", self.strip))
        self.mc = QComboBox()
        self.mc.addItem("C3 (Ableton, Yamaha)", 3)
        self.mc.addItem("C4 (scientific, Roland)", 4)
        self.mc.setCurrentIndex(0 if int(s["middle_c"]) == 3 else 1)
        self.mc.currentIndexChanged.connect(lambda i: self._set("middle_c", self.mc.itemData(i)))
        cl.addWidget(row("Middle C is called", self.mc))
        lay.addWidget(c)

        c, cl = card("Look", "Full colour uses the Push's RGB message; turn it off on old firmware if pads look wrong.")
        self.rgb = QCheckBox("Full RGB colour")
        self.rgb.setChecked(bool(s["full_rgb"]))
        self.rgb.toggled.connect(lambda on: (self._set("full_rgb", on), self.core.repaint_hardware()))
        cl.addWidget(self.rgb)
        self.bright = QSlider(Qt.Horizontal)
        self.bright.setRange(10, 100)
        self.bright.setValue(int(s["brightness"]))
        self.bright.sliderReleased.connect(lambda: (self._set("brightness", self.bright.value()),
                                                    self.core.repaint_hardware()))
        cl.addWidget(row("Pad brightness", self.bright))
        grid = QGridLayout()
        self.swatches = {}
        for i, (key, label) in enumerate(self.COLOR_ROLES):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, k=key: self._pick(k))
            self.swatches[key] = b
            grid.addWidget(b, i // 3, i % 3)
        cl.addLayout(grid)
        h = QHBoxLayout()
        t = QPushButton(theme.icon("lightbulb", theme.TEXT, 16), "Test LEDs")
        t.clicked.connect(core.test_leds)
        rp = QPushButton(theme.icon("rotate-cw", theme.TEXT, 16), "Repaint the Push")
        rp.setToolTip("Resend every light and the display (if something else scribbled on it)")
        rp.clicked.connect(core.repaint_hardware)
        h.addWidget(t)
        h.addWidget(rp)
        h.addStretch(1)
        cl.addLayout(h)
        lay.addWidget(c)
        lay.addStretch(1)
        self._paint_swatches()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll(inner))

    def _set(self, key, value, repaint=True):
        self.core.settings[key] = value
        self.core.changed(repaint)

    def _pick(self, key):
        cur = QColor(*self.core.settings["colors"][key])
        c = QColorDialog.getColor(cur, self, "Pick a pad colour")
        if c.isValid():
            self.core.settings["colors"][key] = [c.red(), c.green(), c.blue()]
            self.core.changed(True)
            self._paint_swatches()

    def _paint_swatches(self):
        for key, b in self.swatches.items():
            r, g, bl = self.core.settings["colors"][key]
            fg = "#000" if (r * 0.3 + g * 0.6 + bl * 0.1) > 140 else "#fff"
            b.setStyleSheet(f"background: rgb({r},{g},{bl}); color:{fg}; border:none; font-weight:600;")


# ===================================================================== Controls page
class ControlsPage(QWidget):
    def __init__(self, core):
        super().__init__()
        self.core = core
        s = core.settings
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(14)
        lay.addWidget(page_header("Knobs, buttons & clock",
                                  "Knobs send CCs on the play channel. Rename them and the Push's display follows."))
        c, cl = card("Knobs")
        self.table = QTableWidget(9, 3)
        self.table.setHorizontalHeaderLabels(["Knob", "Name on the display", "CC"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setMinimumHeight(9 * 36 + 40)
        for i, enc in enumerate(s["encoders"]):
            it = QTableWidgetItem("Master" if i == 8 else f"Knob {i + 1}")
            it.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(i, 0, it)
            self.table.setItem(i, 1, QTableWidgetItem(enc["name"]))
            sp = QSpinBox()
            sp.setRange(0, 127)
            sp.setValue(int(enc["cc"]))
            sp.valueChanged.connect(lambda v, k=i: self._cc(k, v))
            self.table.setCellWidget(i, 2, sp)
        self.table.itemChanged.connect(self._name)
        cl.addWidget(self.table)
        self.relative = QCheckBox("Send relative values (for software that takes endless encoders)")
        self.relative.setChecked(bool(s["encoder_relative"]))
        self.relative.toggled.connect(lambda on: self._set("encoder_relative", on))
        cl.addWidget(self.relative)
        lay.addWidget(c)

        c, cl = card("Buttons", "Push Bridge uses Shift, Scales, Note, Octave, arrows, Accent, Repeat, the "
                                "1/4–1/32t column, Play, Tap Tempo and User. Every other button is yours: it "
                                "sends a CC (number = the button's own CC, value 127/0) so you can MIDI-learn it. "
                                "Send the same CC back and its light follows.")
        self.bch = QSpinBox()
        self.bch.setRange(1, 16)
        self.bch.setValue(int(s["button_channel"]) + 1)
        self.bch.valueChanged.connect(lambda v: self._set("button_channel", v - 1, False))
        cl.addWidget(row("Button channel", self.bch))
        lay.addWidget(c)

        c, cl = card("Clock", "Play on the Push starts and stops MIDI clock at the tempo knob's BPM, so drum "
                              "machines, arps and hardware follow along. Tap Tempo blinks on the beat.")
        self.clock = QComboBox()
        for k, label in (("playing", "Send clock while playing"), ("always", "Send clock all the time"),
                         ("off", "Don't send clock")):
            self.clock.addItem(label, k)
        self.clock.setCurrentIndex(max(0, self.clock.findData(s["clock"])))
        self.clock.currentIndexChanged.connect(lambda i: self._set("clock", self.clock.itemData(i), False))
        cl.addWidget(row("MIDI clock", self.clock))
        lay.addWidget(c)

        if IS_WIN and core.seq is not None:
            c, cl = card("Windows MIDI port for your software",
                         "Windows has no virtual ports, so Push Bridge talks to your software through a loopback "
                         "pair. Automatic finds “Push Bridge App” (Windows 11 MIDI Settings), loopMIDI's "
                         "“Push Bridge” + “Push Bridge Back” (Windows 10), or the default app loopback.")
            from ..hw.ports import is_push1
            from ..hw.winmm import in_names, out_names
            self.wout = QComboBox()
            self.win_ = QComboBox()
            for cb, names, key in ((self.wout, out_names(), "win_out_port"), (self.win_, in_names(), "win_in_port")):
                cb.addItem("Automatic", "")
                for n in names:
                    if n and not is_push1(n):
                        cb.addItem(n, n)
                cb.setCurrentIndex(max(0, cb.findData(s.get(key, ""))))
                cb.currentIndexChanged.connect(self._win_ports)
            cl.addWidget(row("Push Bridge sends on", self.wout))
            cl.addWidget(row("Push Bridge listens on", self.win_))
            self.wlbl = QLabel()
            self.wlbl.setObjectName("muted")
            self.wlbl.setWordWrap(True)
            cl.addWidget(self.wlbl)
            self._win_label()
            lay.addWidget(c)

        c, cl = card("App")
        self.auto = QCheckBox("Start at login (quietly, in the tray)")
        self.auto.setChecked(autostart_enabled())
        self.auto.toggled.connect(set_autostart)
        cl.addWidget(self.auto)
        self.ah = QCheckBox("Step aside automatically while Ableton Live is running" if IS_WIN else
                           "Step aside automatically when Ableton Live connects to the Push")
        self.ah.setToolTip("When another app starts sending to the Push directly (Live under Wine, Bitwig's "
                           "Push script...), Push Bridge goes quiet, then takes over again when it leaves.")
        self.ah.setChecked(bool(s.get("auto_handoff", True)))
        self.ah.toggled.connect(lambda on: self._set("auto_handoff", on, False))
        cl.addWidget(self.ah)
        lay.addWidget(c)
        lay.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll(inner))

    def _set(self, key, value, repaint=True):
        self.core.settings[key] = value
        self.core.changed(repaint)

    def _win_ports(self, *_):
        s = self.core.settings
        s["win_out_port"] = self.wout.currentData() or ""
        s["win_in_port"] = self.win_.currentData() or ""
        seq = self.core.seq
        seq.want_out, seq.want_in = s["win_out_port"], s["win_in_port"]
        seq.open_app_ports()
        self.core.changed(False)
        self._win_label()

    def _win_label(self):
        seq = self.core.seq
        self.wlbl.setText(f"In your DAW or synth, pick “{seq.daw_port}”." if seq.daw_port and not seq.app_error
                          else (seq.app_error or "No loopback port found yet. Health has the two-minute setup."))

    def _cc(self, i, v):
        self.core.settings["encoders"][i]["cc"] = v
        self.core.changed(False)

    def _name(self, item):
        if item.column() == 1:
            self.core.settings["encoders"][item.row()]["name"] = item.text()[:8]
            self.core.engine.render_lcd()
            self.core.changed(False)


# ===================================================================== Health
class HealthPage(QWidget):
    def __init__(self, core):
        super().__init__()
        self.core = core
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)
        top = QHBoxLayout()
        top.addWidget(page_header("Health check", "Every link from the Push to your software, in order."), 1)
        b = QPushButton(theme.icon("rotate-cw", theme.TEXT, 16), "Run again")
        b.clicked.connect(self.refresh)
        rpt = QPushButton(theme.icon("clipboard-copy", theme.TEXT, 16), "Copy report")
        rpt.setToolTip("Copies your versions and these results, ready to paste into a GitHub issue.")
        rpt.clicked.connect(self._copy)
        top.addWidget(b, 0, Qt.AlignTop)
        top.addWidget(rpt, 0, Qt.AlignTop)
        lay.addLayout(top)
        self.box = QVBoxLayout()
        self.box.setSpacing(8)
        holder = QWidget()
        holder.setLayout(self.box)
        lay.addWidget(scroll(holder), 1)
        self.checks = []

    def refresh(self):
        while self.box.count():
            w = self.box.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.checks = health.run(self.core)
        icons = {"ok": ("circle-check", theme.GOOD), "warn": ("circle-alert", theme.WARN),
                 "bad": ("circle-x", theme.BAD), "info": ("info", theme.ACCENT_2)}
        for c in self.checks:
            f = QFrame()
            f.setObjectName("card")
            h = QHBoxLayout(f)
            h.setContentsMargins(14, 10, 14, 10)
            ic = QLabel()
            name, col = icons[c.state]
            ic.setPixmap(theme.icon(name, col, 20).pixmap(20, 20))
            h.addWidget(ic, 0, Qt.AlignTop)
            v = QVBoxLayout()
            t = QLabel(c.name)
            t.setStyleSheet("font-weight:700;")
            d = QLabel(c.detail)
            d.setObjectName("muted")
            d.setWordWrap(True)
            d.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.addWidget(t)
            v.addWidget(d)
            h.addLayout(v, 1)
            self.box.addWidget(f)
        self.box.addStretch(1)

    def _copy(self):
        QApplication.clipboard().setText(health.report(self.core, self.checks or health.run(self.core)))


# ===================================================================== About
class AboutPage(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.addWidget(page_header("About Push Bridge", f"Version {__version__}"))
        c, cl = card()
        t = QLabel(
            "Push Bridge makes the original (2013) Ableton Push a standalone instrument controller on Linux: "
            "in-key and chromatic note layouts with 67 scales (klezmer, Irish/Scottish, jazz, maqam-ish and more), "
            "drums, pressure, the touch strip, eight named knobs, note repeat, MIDI clock and live chord names on "
            "the Push's own display. Any software that takes MIDI can play it.<br><br>"
            "Ableton never published the Push 1 protocol. This builds on community work: "
            "crosslandwa/push-wrapper, Carlborg/hardpush, the pushmod blog and Adam Murray's palette notes.<br><br>"
            "Not affiliated with Ableton or Akai. Licensed GPL-3.0-or-later. © 2026 Fancy Butler.")
        t.setWordWrap(True)
        t.setTextFormat(Qt.RichText)
        cl.addWidget(t)
        lay.addWidget(c)
        lay.addStretch(1)


# ===================================================================== sidebar status
class Mini(QWidget):
    """Bottom of the sidebar: connection, what you're playing, MIDI lights."""

    def __init__(self, core):
        super().__init__()
        self.core = core
        self.setFixedHeight(118)
        t = QTimer(self)
        t.timeout.connect(self.update)
        t.start(50)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self.core.settings
        r = QRectF(0, 0, self.width(), 84)
        p.setPen(QColor(theme.LINE))
        p.setBrush(QColor(theme.CARD))
        p.drawRoundedRect(r, 12, 12)
        f = QFont(self.font())
        f.setPixelSize(22)
        f.setWeight(QFont.Black)
        p.setFont(f)
        conn = self.core.device.connected or self.core.demo
        p.setPen(QColor(theme.ACCENT) if conn else QColor(theme.MUTED))
        if s["mode"] == "notes":
            big = T.pc_name(int(s["root"]), int(s["root"]))
            small = s["scale"]
        else:
            big, small = "Drums", f"from {T.note_name(int(s['drum_base']), int(s['middle_c']))}"
        p.drawText(r.adjusted(12, 8, -12, -40), Qt.AlignLeft | Qt.AlignVCenter, big)
        f.setPixelSize(11)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor(theme.MUTED))
        p.drawText(r.adjusted(12, 44, -12, -8), Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
                   p.fontMetrics().elidedText(small, Qt.ElideRight, int(r.width() - 24)))
        now = time.time()
        x = 6.0
        f.setPixelSize(10)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        p.setFont(f)
        for label, t, col in (("PUSH", self.core.device.last_rx, theme.ACCENT_2), ("MIDI OUT", self.core.last_out, theme.ACCENT)):
            a = max(0.0, 1 - (now - t) / 0.25)
            c = QColor(col)
            c.setAlphaF(0.3 + 0.7 * a)
            p.setPen(Qt.NoPen)
            p.setBrush(c if a > 0 else QColor(theme.LINE))
            p.drawEllipse(QRectF(x, 100, 8, 8))
            p.setPen(QColor(theme.TEXT) if a > 0 else QColor(theme.MUTED))
            p.drawText(int(x + 14), 108, label)
            x += 26 + p.fontMetrics().horizontalAdvance(label)
        p.end()


# ===================================================================== window
class MainWindow(QMainWindow):
    def __init__(self, core):
        super().__init__()
        self.core = core
        self.setWindowTitle("Push Bridge")
        self.setWindowIcon(theme.icon("pads", theme.ACCENT, 64))
        self.resize(1240, 820)
        self.setMinimumSize(760, 560)
        self.ev = Events()
        root = QWidget()
        root.setObjectName("root")
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(208)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 16, 12, 14)
        sl.setSpacing(4)
        brand = QLabel(f"Push Bridge <span style='color:{theme.MUTED}; font-weight:600'>{__version__}</span>")
        brand.setObjectName("brand")
        brand.setTextFormat(Qt.RichText)
        sub = QLabel("Ableton Push 1, reborn")
        sub.setObjectName("brandSub")
        sl.addWidget(brand)
        sl.addWidget(sub)
        sl.addSpacing(14)

        self.play_page = PlayPage(core)
        self.pads_page = PadsPage(core)
        self.controls_page = ControlsPage(core)
        self.health_page = HealthPage(core)
        self.about_page = AboutPage()
        self.stack = QStackedWidget()
        self.navs = []
        for page, icon_name, label in ((self.play_page, "pads", "Play"), (self.pads_page, "keyboard-music", "Pads && strip"),
                                       (self.controls_page, "sliders-horizontal", "Knobs && buttons"),
                                       (self.health_page, "heart-pulse", "Health"), (self.about_page, "info", "About")):
            self.stack.addWidget(page)
            b = QToolButton()
            b.setObjectName("nav")
            b.setText(label)
            b.setIcon(theme.icon(icon_name, theme.MUTED, 18))
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setCheckable(True)
            b.setSizePolicy(b.sizePolicy().horizontalPolicy().Expanding, b.sizePolicy().verticalPolicy())
            b.clicked.connect(lambda _=False, p=page: self.go_page(p))
            self.navs.append((b, page, icon_name))
            sl.addWidget(b)
        sl.addStretch(1)
        sl.addWidget(Mini(core))
        h.addWidget(side)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.tray = Tray(self) if core.settings.get("tray", True) and Tray.available() else None
        self.ev.changed.connect(self._sync)
        self.ev.status.connect(self._status)
        core.engine.on_change = self._engine_changed
        core.status_listeners.append(lambda st, d: self.ev.status.emit(st, d))
        self._pending = False
        self.go_page(self.play_page)
        self._status(*core.status)

    def _engine_changed(self):
        # from any thread; coalesce bursts into one GUI update
        if not self._pending:
            self._pending = True
            self.ev.changed.emit()

    def _sync(self):
        self._pending = False
        self.play_page.sync()

    def _status(self, state, detail):
        self.play_page.set_status(state, detail)
        self.play_page.sync()
        if self.tray:
            self.tray.set_state(state, detail)
        if self.stack.currentWidget() is self.health_page:
            self.health_page.refresh()

    def go_page(self, page):
        self.stack.setCurrentWidget(page)
        for b, p, icon_name in self.navs:
            on = p is page
            b.setChecked(on)
            b.setIcon(theme.icon(icon_name, theme.ACCENT if on else theme.MUTED, 18))
        if page is self.health_page:
            self.health_page.refresh()

    def go(self, i):
        self.go_page(self.navs[i][1])

    def show_window(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        if self.tray:
            self.tray.hide()
        QApplication.instance().quit()

    def closeEvent(self, e):
        if self.tray:
            e.ignore()
            self.hide()
        else:
            e.accept()
            QApplication.instance().quit()
