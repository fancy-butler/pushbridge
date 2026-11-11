# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fancy Butler
from __future__ import annotations

import copy
import json
from pathlib import Path

from ..platform_util import config_dir

CONFIG_DIR = config_dir()
SETTINGS = CONFIG_DIR / "settings.json"

DEFAULT_ENCODERS = [
    {"name": "Cutoff", "cc": 74}, {"name": "Reso", "cc": 71}, {"name": "Attack", "cc": 73},
    {"name": "Release", "cc": 72}, {"name": "Mod", "cc": 1}, {"name": "Expr", "cc": 11},
    {"name": "Reverb", "cc": 91}, {"name": "Chorus", "cc": 93},
    {"name": "Volume", "cc": 7},     # master encoder
]

DEFAULTS = {
    # playing
    "mode": "notes",                 # notes | drums
    "root": 0,
    "scale": "Major (Ionian)",
    "layout": "4ths",                # 4ths | 3rds | seq
    "in_key": True,
    "octave": 0,                     # bottom-left pad = root + 36 + 12 * octave
    "drum_base": 36,
    "channel": 0,                    # 0-15, notes mode
    "drum_channel": 9,               # drums mode: channel 10, the General MIDI drum channel
    "velocity_curve": "linear",      # linear | soft | hard | fixed
    "fixed_velocity": 100,
    "aftertouch": "poly",            # poly | channel | off
    "strip": "pitch",                # pitch | mod | off
    "middle_c": 3,                   # 3 = Ableton (60 = C3), 4 = scientific (60 = C4)
    "repeat_div": 40,                # time-division button cc (1/16)
    # controls
    "encoders": DEFAULT_ENCODERS,
    "encoder_values": [0, 0, 0, 0, 0, 0, 0, 0, 100],
    "encoder_relative": False,
    "button_channel": 15,            # buttons we don't use go out as CCs here
    "tempo": 120.0,
    "clock": "playing",              # off | playing | always
    # look
    "full_rgb": True,
    "brightness": 100,
    "colors": {
        "root": [40, 110, 255], "scale": [150, 150, 160], "out": [0, 0, 0],
        "pressed": [40, 255, 90], "feedback": [255, 140, 20],
    },
    # app
    "tray": True,
    "auto_handoff": True,            # step aside when Ableton Live connects to / is running with the Push
    "win_out_port": "",              # Windows: loopback port we send to ("" = automatic)
    "win_in_port": "",               # Windows: loopback port we listen on
}


def load() -> dict:
    s = copy.deepcopy(DEFAULTS)
    try:
        saved = json.loads(SETTINGS.read_text())
        if isinstance(saved, dict):
            for k, v in saved.items():
                if k in s and isinstance(s[k], dict) and isinstance(v, dict):
                    s[k].update(v)
                elif k in s:
                    s[k] = v
    except (OSError, ValueError):
        pass
    if len(s["encoders"]) != 9:
        s["encoders"] = copy.deepcopy(DEFAULT_ENCODERS)
    if len(s["encoder_values"]) != 9:
        s["encoder_values"] = list(DEFAULTS["encoder_values"])
    return s


def save(s: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=2))
    tmp.replace(SETTINGS)
