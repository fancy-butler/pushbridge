# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fancy Butler
"""Checks every link from the Push to your software, in order, in plain words."""
from __future__ import annotations

import platform
import re
import time
from dataclasses import dataclass

from . import __version__
from .hw import alsa


@dataclass
class Check:
    name: str
    state: str          # ok | warn | bad | info
    detail: str


def parse_seq_clients(text: str) -> dict:
    """/proc/asound/seq/clients -> {client: {"name": str, "ports": {port: {"name", "to", "from"}}}}"""
    clients: dict = {}
    cur = port = None
    for line in text.splitlines():
        m = re.match(r'Client\s+(\d+)\s*:\s*"(.*)"', line)
        if m:
            cur = int(m.group(1))
            clients[cur] = {"name": m.group(2), "ports": {}}
            port = None
            continue
        m = re.match(r'\s+Port\s+(\d+)\s*:\s*"(.*)"', line)
        if m and cur is not None:
            port = int(m.group(1))
            clients[cur]["ports"][port] = {"name": m.group(2), "to": [], "from": []}
            continue
        m = re.match(r"\s+(Connecting To|Connected From):\s*(.*)", line)
        if m and cur is not None and port is not None:
            addrs = []
            for a in m.group(2).split(","):
                mm = re.match(r"\s*(\d+):(\d+)", a)
                if mm:
                    addrs.append((int(mm.group(1)), int(mm.group(2))))
            clients[cur]["ports"][port]["to" if m.group(1) == "Connecting To" else "from"] += addrs
    return clients


def run(core) -> list[Check]:
    out: list[Check] = []
    if core.demo:
        out.append(Check("Demo mode", "info", "No hardware is used. Start without --demo to talk to a real Push."))
        return out
    if not alsa.seq_available():
        out.append(Check("ALSA sequencer", "bad",
                         "/dev/snd/seq is missing. Load it with: sudo modprobe snd-seq"))
        return out
    out.append(Check("ALSA sequencer", "ok", "/dev/snd/seq is there"))
    if core.seq is None:
        out.append(Check("Push Bridge MIDI port", "bad", core.midi_error or "Couldn't open the sequencer"))
        return out
    out.append(Check("Push Bridge MIDI port", "ok",
                     f"“Push Bridge › Push 1” is at {core.seq.address}. Pick it as a MIDI input in your software."))
    dev = core.device
    if not dev.connected:
        out.append(Check("Push found", "bad",
                         "No Ableton Push (1st gen) on the sequencer. Check it's powered (the USB bus alone "
                         "can't light everything; use the power supply), then the cable. `aconnect -l` should "
                         "list “Ableton Push”."))
        return out
    out.append(Check("Push found", "ok", f"{dev.name}: " + ", ".join(f"{p.name} ({p.client}:{p.port})" for p in dev.ports)))
    if dev.last_rx:
        out.append(Check("Push talking to us", "ok", f"Last message {time.time() - dev.last_rx:.0f} s ago"))
    else:
        out.append(Check("Push talking to us", "warn", "Nothing received yet. Hit a pad or turn a knob, then run this again."))
    if dev.identity:
        out.append(Check("Firmware answered", "ok", f"Identity reply: {dev.identity}"))
    else:
        out.append(Check("Firmware answered", "info", "No identity reply (harmless; some firmware doesn't answer)."))

    clients = parse_seq_clients(alsa.connections_text())
    if clients:
        me = clients.get(core.seq.client, {}).get("ports", {}).get(core.seq.public)
        if me:
            readers = sorted({clients.get(c, {}).get("name", str(c)) for c, _ in me["to"]})
            writers = sorted({clients.get(c, {}).get("name", str(c)) for c, _ in me["from"]})
            if readers:
                out.append(Check("Apps listening", "ok", ", ".join(readers)))
            else:
                out.append(Check("Apps listening", "warn",
                                 "Nothing is reading Push Bridge yet. Choose “Push Bridge › Push 1” as a MIDI "
                                 "input in your DAW or synth (with PipeWire, it may be called “Push Bridge”)."))
            if writers:
                out.append(Check("Apps sending back", "info", ", ".join(writers) + " (lights and feedback)"))
        others = set()
        for p in dev.ports:
            info = clients.get(p.client, {}).get("ports", {}).get(p.port)
            if not info:
                continue
            for c, _ in info["to"] + info["from"]:
                if c not in (core.seq.client, 0):
                    others.add(clients.get(c, {}).get("name", str(c)))
        others.discard("Midi Through")
        pw = {o for o in others if "pipewire" in o.lower()}
        others -= pw
        if others:
            out.append(Check("Other apps on the Push", "warn",
                             "Also connected straight to the Push: " + ", ".join(sorted(others)) +
                             ". They'll fight Push Bridge over the lights and display. In that app, pick "
                             "“Push Bridge › Push 1” instead of the Push itself."))
        else:
            out.append(Check("Other apps on the Push", "ok", "Push Bridge has it to itself"
                             + (" (PipeWire's bridge is just listening)" if pw else "")))
    return out


def report(core, checks: list[Check]) -> str:
    lines = [f"Push Bridge {__version__}", f"Python {platform.python_version()} · {platform.platform()}"]
    try:
        import PySide6
        lines.append(f"PySide6 {PySide6.__version__}")
    except Exception:
        pass
    lines.append("")
    for c in checks:
        lines.append(f"[{c.state.upper():4}] {c.name}: {c.detail}")
    return "\n".join(lines)
