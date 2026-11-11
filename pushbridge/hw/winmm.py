# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fancy Butler
"""Windows MIDI through WinMM (ctypes, no compiled extensions).

Windows has no virtual MIDI ports like ALSA's, so the "public" side is a
loopback port pair:
  * Windows 11 with Windows MIDI Services: a loopback pair made in the
    MIDI Settings app (built in, no drivers), or the default app loopbacks
  * Windows 10: two loopMIDI ports
On Windows 11 with Windows MIDI Services every port is multi-client, so Live
and Push Bridge can both open the Push.  On older MIDI stacks only one app may
open it, which is why hand-off releases the Push completely.
"""
from __future__ import annotations

import ctypes as C
import queue
import re
import threading
import time
import traceback
from ctypes import wintypes as W
from typing import Callable, Optional

from .ports import CAP_READ, CAP_WRITE, PortInfo, is_push1

CALLBACK_FUNCTION = 0x30000
MIM_DATA, MIM_LONGDATA = 0x3C3, 0x3C4
MHDR_DONE = 1
MMSYSERR_ALLOCATED = 4
SYSEX_BUF = 1024
SYSEX_BUFS = 8


class MidiError(RuntimeError):
    pass


class MIDIINCAPSW(C.Structure):
    _fields_ = [("wMid", W.WORD), ("wPid", W.WORD), ("vDriverVersion", C.c_uint),
                ("szPname", C.c_wchar * 32), ("dwSupport", W.DWORD)]


class MIDIOUTCAPSW(C.Structure):
    _fields_ = [("wMid", W.WORD), ("wPid", W.WORD), ("vDriverVersion", C.c_uint),
                ("szPname", C.c_wchar * 32), ("wTechnology", W.WORD), ("wVoices", W.WORD),
                ("wNotes", W.WORD), ("wChannelMask", W.WORD), ("dwSupport", W.DWORD)]


class MIDIHDR(C.Structure):
    _fields_ = [("lpData", C.c_void_p), ("dwBufferLength", W.DWORD), ("dwBytesRecorded", W.DWORD),
                ("dwUser", C.c_size_t), ("dwFlags", W.DWORD), ("lpNext", C.c_void_p),
                ("reserved", C.c_size_t), ("dwOffset", W.DWORD), ("dwReserved", C.c_size_t * 8)]


MidiInProc = getattr(C, "WINFUNCTYPE", C.CFUNCTYPE)(   # CFUNCTYPE only so tests import on Linux
    None, C.c_void_p, C.c_uint, C.c_size_t, C.c_size_t, C.c_size_t)
_mm = None


def mm():
    global _mm
    if _mm is None:
        _mm = C.WinDLL("winmm")
        H = C.POINTER(C.c_void_p)
        _mm.midiInOpen.argtypes = [H, C.c_uint, C.c_size_t, C.c_size_t, W.DWORD]
        _mm.midiOutOpen.argtypes = [H, C.c_uint, C.c_size_t, C.c_size_t, W.DWORD]
        for f in ("midiInStart", "midiInStop", "midiInReset", "midiInClose",
                  "midiOutReset", "midiOutClose"):
            getattr(_mm, f).argtypes = [C.c_void_p]
        for f in ("midiInPrepareHeader", "midiInUnprepareHeader", "midiInAddBuffer",
                  "midiOutPrepareHeader", "midiOutUnprepareHeader", "midiOutLongMsg"):
            getattr(_mm, f).argtypes = [C.c_void_p, C.POINTER(MIDIHDR), C.c_uint]
        _mm.midiOutShortMsg.argtypes = [C.c_void_p, W.DWORD]
        _mm.midiInGetDevCapsW.argtypes = [C.c_size_t, C.POINTER(MIDIINCAPSW), C.c_uint]
        _mm.midiOutGetDevCapsW.argtypes = [C.c_size_t, C.POINTER(MIDIOUTCAPSW), C.c_uint]
    return _mm


def in_names() -> list[str]:
    out = []
    for i in range(mm().midiInGetNumDevs()):
        caps = MIDIINCAPSW()
        out.append(caps.szPname if mm().midiInGetDevCapsW(i, C.byref(caps), C.sizeof(caps)) == 0 else "")
    return out


def out_names() -> list[str]:
    out = []
    for i in range(mm().midiOutGetNumDevs()):
        caps = MIDIOUTCAPSW()
        out.append(caps.szPname if mm().midiOutGetDevCapsW(i, C.byref(caps), C.sizeof(caps)) == 0 else "")
    return out


def short_len(status: int) -> int:
    if status >= 0xF8:
        return 1
    if status & 0xF0 in (0xC0, 0xD0) or status in (0xF1, 0xF3):
        return 2
    if status in (0xF6,):
        return 1
    return 3


# ------------------------------------------------------------------ app port choice
def pick_app_ports(ins: list[str], outs: list[str], want_out: str = "", want_in: str = "") -> tuple[str, str, str]:
    """Choose (our output, our input, what the DAW should pick).

    Conventions, in order:
      1. names saved in settings
      2. Windows MIDI Services loopback pair "Push Bridge App" ⇄ "Push Bridge"
      3. two loopMIDI ports "Push Bridge" (we send) and "Push Bridge Back" (we listen)
      4. the default app loopback pair, side A (the DAW uses side B)
    """
    li = {n.lower(): n for n in ins if n}
    lo = {n.lower(): n for n in outs if n}
    if want_out and want_out.lower() in lo:
        o = lo[want_out.lower()]
        i = li.get((want_in or want_out).lower(), "")
        return o, i, partner_name(o)
    if "push bridge app" in lo:
        return lo["push bridge app"], li.get("push bridge app", ""), "Push Bridge"
    if "push bridge" in lo and "push bridge back" in li:
        return lo["push bridge"], li["push bridge back"], "Push Bridge (input) / Push Bridge Back (output)"
    for key, name in lo.items():
        if "loopback" in key and re.search(r"\(a\)|\ba\b", key):
            return name, li.get(key, ""), partner_name(name)
    return "", "", ""


def partner_name(ours: str) -> str:
    if re.search(r"\(A\)", ours, re.I):
        return re.sub(r"\(A\)", "(B)", ours, flags=re.I)
    if ours.lower().endswith(" app"):
        return ours[:-4]
    return ours


# ------------------------------------------------------------------ ports
class _In:
    def __init__(self, dev_id: int, name: str, sink: "queue.Queue", tag: str):
        self.name, self.tag, self.sink = name, tag, sink
        self.h = C.c_void_p()
        self._cb = MidiInProc(self._proc)
        self._closing = False
        rc = mm().midiInOpen(C.byref(self.h), dev_id, C.cast(self._cb, C.c_void_p).value, 0, CALLBACK_FUNCTION)
        if rc:
            raise MidiError(f"Couldn't open MIDI input “{name}” (error {rc}"
                            + (": another app has it" if rc == MMSYSERR_ALLOCATED else "") + ")")
        self._bufs = []
        for _ in range(SYSEX_BUFS):
            buf = C.create_string_buffer(SYSEX_BUF)
            hdr = MIDIHDR()
            hdr.lpData = C.addressof(buf)
            hdr.dwBufferLength = SYSEX_BUF
            mm().midiInPrepareHeader(self.h, C.byref(hdr), C.sizeof(hdr))
            mm().midiInAddBuffer(self.h, C.byref(hdr), C.sizeof(hdr))
            self._bufs.append((buf, hdr))
        self._partial = b""
        mm().midiInStart(self.h)

    def _proc(self, _h, msg, _inst, p1, _p2):
        # WinMM callback thread: keep it tiny, no MIDI calls from here
        if msg == MIM_DATA:
            self.sink.put((self, "short", p1))
        elif msg == MIM_LONGDATA:
            self.sink.put((self, "long", p1))

    def handle(self, kind: str, p1: int) -> Optional[bytes]:
        """Runs on our worker thread."""
        if kind == "short":
            st = p1 & 0xFF
            return bytes((st, (p1 >> 8) & 0x7F, (p1 >> 16) & 0x7F))[:short_len(st)]
        hdr = MIDIHDR.from_address(p1)
        data = C.string_at(hdr.lpData, hdr.dwBytesRecorded) if hdr.dwBytesRecorded else b""
        if not self._closing:
            mm().midiInAddBuffer(self.h, C.byref(hdr), C.sizeof(hdr))
        if not data:
            return None
        self._partial += data
        if self._partial.endswith(b"\xf7") or len(self._partial) > 1 << 16:
            msg, self._partial = self._partial, b""
            return msg
        return None

    def close(self):
        self._closing = True
        try:
            mm().midiInStop(self.h)
            mm().midiInReset(self.h)
            for _buf, hdr in self._bufs:
                mm().midiInUnprepareHeader(self.h, C.byref(hdr), C.sizeof(hdr))
            mm().midiInClose(self.h)
        except Exception:
            pass


class _Out:
    def __init__(self, dev_id: int, name: str):
        self.name = name
        self.h = C.c_void_p()
        rc = mm().midiOutOpen(C.byref(self.h), dev_id, 0, 0, 0)
        if rc:
            raise MidiError(f"Couldn't open MIDI output “{name}” (error {rc}"
                            + (": another app has it" if rc == MMSYSERR_ALLOCATED else "") + ")")
        self.lock = threading.Lock()

    def send(self, msg: bytes):
        with self.lock:
            if msg[0] == 0xF0:
                buf = C.create_string_buffer(bytes(msg), len(msg))
                hdr = MIDIHDR()
                hdr.lpData = C.addressof(buf)
                hdr.dwBufferLength = len(msg)
                mm().midiOutPrepareHeader(self.h, C.byref(hdr), C.sizeof(hdr))
                if mm().midiOutLongMsg(self.h, C.byref(hdr), C.sizeof(hdr)) == 0:
                    t0 = time.monotonic()
                    while not hdr.dwFlags & MHDR_DONE and time.monotonic() - t0 < 1.0:
                        time.sleep(0.0002)
                mm().midiOutUnprepareHeader(self.h, C.byref(hdr), C.sizeof(hdr))
            else:
                b = list(msg) + [0, 0]
                mm().midiOutShortMsg(self.h, b[0] | (b[1] << 8) | (b[2] << 16))

    def close(self):
        try:
            mm().midiOutReset(self.h)
            mm().midiOutClose(self.h)
        except Exception:
            pass


# ------------------------------------------------------------------ backend
class WinMidi:
    """Same shape as alsa.Seq so the rest of the app doesn't care."""
    client = -1
    public = 0
    multi_client = False        # set by core after detecting Windows MIDI Services
    release_on_handoff = True

    def __init__(self, want_out: str = "", want_in: str = ""):
        self.on_push: Optional[Callable[[bytes, int], None]] = None
        self.on_app: Optional[Callable[[bytes], None]] = None
        self.on_change: Optional[Callable[[], None]] = None
        self.want_out, self.want_in = want_out, want_in
        self._q: queue.Queue = queue.Queue()
        self._push_in: list[_In] = []
        self._push_out: list[_Out] = []
        self._app_in: Optional[_In] = None
        self._app_out: Optional[_Out] = None
        self.app_out_name = self.app_in_name = self.daw_port = ""
        self.app_error = ""
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._snapshot = (tuple(in_names()), tuple(out_names()))
        self.open_app_ports()
        threading.Thread(target=self._worker, name="pushbridge-winmm", daemon=True).start()
        threading.Thread(target=self._poll, name="pushbridge-winmm-poll", daemon=True).start()

    @property
    def address(self) -> str:
        return self.daw_port or "(no loopback port yet)"

    # -------------------------------------------------- app side
    def open_app_ports(self):
        with self._lock:
            for p in (self._app_in, self._app_out):
                if p:
                    p.close()
            self._app_in = self._app_out = None
            ins, outs = in_names(), out_names()
            o, i, daw = pick_app_ports(ins, outs, self.want_out, self.want_in)
            self.app_out_name, self.app_in_name, self.daw_port = o, i, daw
            self.app_error = ""
            if not o:
                self.app_error = "No loopback port for your software yet (see Health)"
                return
            try:
                self._app_out = _Out(outs.index(o), o)
                if i:
                    self._app_in = _In(ins.index(i), i, self._q, "app")
            except MidiError as e:
                self.app_error = str(e)

    # -------------------------------------------------- push side
    def ports(self) -> list[PortInfo]:
        out = [PortInfo(0, i, n, n, CAP_READ) for i, n in enumerate(in_names())]
        out += [PortInfo(0, 1000 + i, n, n, CAP_WRITE) for i, n in enumerate(out_names())]
        return [p for p in out if p.name]

    def connect_push(self, ports: list[PortInfo]):
        self.disconnect_push()
        try:
            for p in ports:
                if p.caps & CAP_READ:
                    self._push_in.append(_In(p.port, p.name, self._q, "push"))
                elif p.caps & CAP_WRITE:
                    self._push_out.append(_Out(p.port - 1000, p.name))
        except MidiError:
            self.disconnect_push()
            raise

    def disconnect_push(self):
        with self._lock:
            for p in self._push_in + self._push_out:
                p.close()
            self._push_in, self._push_out = [], []

    def to_push(self, msg: bytes):
        for o in list(self._push_out):
            try:
                o.send(msg)
            except Exception:
                pass

    def to_apps(self, msg: bytes):
        o = self._app_out
        if o:
            try:
                o.send(msg)
            except Exception:
                pass

    # -------------------------------------------------- threads
    def _worker(self):
        while not self._stop.is_set():
            try:
                port, kind, p1 = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                msg = port.handle(kind, p1)
                if not msg:
                    continue
                if port.tag == "push" and self.on_push:
                    self.on_push(msg, 0)
                elif port.tag == "app" and self.on_app:
                    self.on_app(msg)
            except Exception:
                traceback.print_exc()

    def _poll(self):
        """WinMM has no hot-plug events we can get without a window: poll names."""
        while not self._stop.wait(1.5):
            try:
                snap = (tuple(in_names()), tuple(out_names()))
            except Exception:
                continue
            if snap != self._snapshot:
                self._snapshot = snap
                if not self._app_out or self.app_out_name not in snap[1]:
                    self.open_app_ports()
                if self.on_change:
                    self.on_change()

    def close(self):
        self._stop.set()
        self.disconnect_push()
        for p in (self._app_in, self._app_out):
            if p:
                p.close()


def push_names() -> list[str]:
    return [n for n in in_names() if is_push1(n)]
