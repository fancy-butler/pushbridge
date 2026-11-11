# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fancy Butler
"""Tiny ctypes bindings to the ALSA sequencer.  No compiled extensions, so the
app installs the same way on Arch, Fedora and Debian/Ubuntu.

One sequencer client ("Push Bridge") owns two ports:
  * a hidden link port, subscribed to and from the Push's own ports
  * the public port other apps (Bitwig, Reaper, Ardour, Noodle, a synth...) see
Going through the sequencer (not rawmidi) means we never lock the Push away
from other software.
"""
from __future__ import annotations

import ctypes as C
import ctypes.util
import os
import select
import threading
import traceback
from typing import Callable, Optional

_lib = None


def lib():
    global _lib
    if _lib is None:
        name = ctypes.util.find_library("asound") or "libasound.so.2"
        _lib = C.CDLL(name)
        _lib.snd_strerror.restype = C.c_char_p
        _lib.snd_seq_client_info_get_name.restype = C.c_char_p
        _lib.snd_seq_port_info_get_name.restype = C.c_char_p
        _lib.snd_seq_port_info_get_capability.restype = C.c_uint
        _lib.snd_seq_port_info_get_type.restype = C.c_uint
    return _lib


class AlsaError(RuntimeError):
    pass


def _check(rc: int, what: str) -> int:
    if rc < 0:
        raise AlsaError(f"{what}: {lib().snd_strerror(rc).decode()}")
    return rc


def seq_available() -> bool:
    return os.path.exists("/dev/snd/seq")


# ---------------------------------------------------------------- event struct
class _Addr(C.Structure):
    _fields_ = [("client", C.c_ubyte), ("port", C.c_ubyte)]


class SeqEvent(C.Structure):
    # snd_seq_event_t: 28 bytes (snd_seq_ev_ext is packed in the kernel ABI)
    _fields_ = [
        ("type", C.c_ubyte), ("flags", C.c_ubyte), ("tag", C.c_ubyte), ("queue", C.c_ubyte),
        ("time_a", C.c_uint), ("time_b", C.c_uint),
        ("source", _Addr), ("dest", _Addr),
        ("data", C.c_ubyte * 12),
    ]


assert C.sizeof(SeqEvent) == 28

EV_NOTEON, EV_NOTEOFF, EV_KEYPRESS = 6, 7, 8
EV_CONTROLLER, EV_PGMCHANGE, EV_CHANPRESS, EV_PITCHBEND = 10, 11, 12, 13
EV_START, EV_CONTINUE, EV_STOP, EV_CLOCK = 30, 31, 32, 36
EV_CLIENT_START, EV_CLIENT_EXIT, EV_PORT_START, EV_PORT_EXIT = 60, 61, 63, 64
EV_SYSEX = 130
FLAG_VARIABLE = 1 << 2
ADDR_UNKNOWN, ADDR_SUBSCRIBERS = 253, 254
QUEUE_DIRECT = 253
CAP_READ, CAP_WRITE, CAP_SUBS_READ, CAP_SUBS_WRITE, CAP_NO_EXPORT = 1, 2, 1 << 5, 1 << 6, 1 << 7
TYPE_MIDI_GENERIC, TYPE_HARDWARE, TYPE_APPLICATION = 1 << 1, 1 << 16, 1 << 20
OPEN_DUPLEX = 3
POLLIN = 1
REALTIME = {0xFA: EV_START, 0xFB: EV_CONTINUE, 0xFC: EV_STOP, 0xF8: EV_CLOCK}
REALTIME_BACK = {v: k for k, v in REALTIME.items()}


def _put_u32(ev: SeqEvent, off: int, v: int, signed: bool = False):
    C.memmove(C.addressof(ev.data) + off, C.byref((C.c_int if signed else C.c_uint)(v)), 4)


def _get(ev: SeqEvent, off: int, signed: bool = False) -> int:
    return (C.c_int if signed else C.c_uint).from_buffer_copy(bytes(ev.data[off:off + 4])).value


def encode(msg: bytes) -> tuple[Optional[SeqEvent], object]:
    """Raw MIDI message -> (seq event, buffer to keep alive for sysex)."""
    ev = SeqEvent()
    keep = None
    st = msg[0]
    if st == 0xF0:
        keep = C.create_string_buffer(bytes(msg), len(msg))
        ev.type = EV_SYSEX
        ev.flags = FLAG_VARIABLE
        _put_u32(ev, 0, len(msg))
        C.memmove(C.addressof(ev.data) + 4, C.byref(C.c_void_p(C.addressof(keep))), C.sizeof(C.c_void_p))
    elif st in REALTIME:
        ev.type = REALTIME[st]
    else:
        kind, ch = st & 0xF0, st & 0x0F
        d1 = msg[1] & 0x7F if len(msg) > 1 else 0
        d2 = msg[2] & 0x7F if len(msg) > 2 else 0
        if kind in (0x90, 0x80, 0xA0):
            ev.type = {0x90: EV_NOTEON, 0x80: EV_NOTEOFF, 0xA0: EV_KEYPRESS}[kind]
            ev.data[0], ev.data[1], ev.data[2] = ch, d1, d2
        elif kind == 0xB0:
            ev.type = EV_CONTROLLER
            ev.data[0] = ch
            _put_u32(ev, 4, d1)
            _put_u32(ev, 8, d2, True)
        elif kind in (0xC0, 0xD0):
            ev.type = EV_PGMCHANGE if kind == 0xC0 else EV_CHANPRESS
            ev.data[0] = ch
            _put_u32(ev, 8, d1, True)
        elif kind == 0xE0:
            ev.type = EV_PITCHBEND
            ev.data[0] = ch
            _put_u32(ev, 8, ((d2 << 7) | d1) - 8192, True)
        else:
            return None, None
    ev.queue = QUEUE_DIRECT
    ev.dest.client, ev.dest.port = ADDR_SUBSCRIBERS, ADDR_UNKNOWN
    return ev, keep


def decode(ev: SeqEvent) -> Optional[bytes]:
    """Seq event -> raw MIDI bytes."""
    t = ev.type
    ch = ev.data[0] & 0x0F
    if t in (EV_NOTEON, EV_NOTEOFF, EV_KEYPRESS):
        kind = {EV_NOTEON: 0x90, EV_NOTEOFF: 0x80, EV_KEYPRESS: 0xA0}[t]
        return bytes((kind | ch, ev.data[1] & 0x7F, ev.data[2] & 0x7F))
    if t == EV_CONTROLLER:
        return bytes((0xB0 | ch, _get(ev, 4) & 0x7F, max(0, min(127, _get(ev, 8, True)))))
    if t in (EV_PGMCHANGE, EV_CHANPRESS):
        return bytes(((0xC0 if t == EV_PGMCHANGE else 0xD0) | ch, max(0, min(127, _get(ev, 8, True)))))
    if t == EV_PITCHBEND:
        v = max(0, min(16383, _get(ev, 8, True) + 8192))
        return bytes((0xE0 | ch, v & 0x7F, v >> 7))
    if t == EV_SYSEX:
        n = _get(ev, 0)
        ptr = C.c_void_p.from_buffer_copy(bytes(ev.data[4:4 + C.sizeof(C.c_void_p)])).value
        if ptr and 0 < n < 1 << 16:
            return C.string_at(ptr, n)
        return None
    if t in REALTIME_BACK:
        return bytes((REALTIME_BACK[t],))
    return None


# ---------------------------------------------------------------- discovery
from .ports import PortInfo, is_push1  # noqa: E402,F401  (re-exported)


class Seq:
    """One sequencer client: hidden link port to the Push + public port for apps.

    on_push(bytes) gets everything the Push sends; on_app(bytes) everything apps
    send to the public port; on_change() fires when clients/ports come and go."""

    multi_client = True          # the sequencer never locks a port to one app
    release_on_handoff = True    # unsubscribe too, so apps that open the raw device can get it

    def __init__(self, client_name: str = "Push Bridge", port_name: str = "Push 1"):
        L = lib()
        self._seq = C.c_void_p()
        _check(L.snd_seq_open(C.byref(self._seq), b"default", OPEN_DUPLEX, 1), "snd_seq_open")
        L.snd_seq_set_client_name(self._seq, client_name.encode())
        # big enough for a full-screen LCD redraw in one go
        L.snd_seq_set_output_buffer_size(self._seq, 1 << 16)
        L.snd_seq_set_input_buffer_size(self._seq, 1 << 16)
        self.client = L.snd_seq_client_id(self._seq)
        self.link = _check(L.snd_seq_create_simple_port(
            self._seq, b"Push link", CAP_READ | CAP_WRITE | CAP_NO_EXPORT, TYPE_APPLICATION), "link port")
        self.public = _check(L.snd_seq_create_simple_port(
            self._seq, port_name.encode(), CAP_READ | CAP_WRITE | CAP_SUBS_READ | CAP_SUBS_WRITE,
            TYPE_MIDI_GENERIC | TYPE_APPLICATION), "public port")
        self.announce = _check(L.snd_seq_create_simple_port(
            self._seq, b"announce", CAP_WRITE | CAP_NO_EXPORT, TYPE_APPLICATION), "announce port")
        try:
            L.snd_seq_connect_from(self._seq, self.announce, 0, 1)   # System:Announce
        except Exception:
            pass
        self.on_push: Optional[Callable[[bytes, int], None]] = None
        self.on_app: Optional[Callable[[bytes], None]] = None
        self.on_change: Optional[Callable[[], None]] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._reader, name="pushbridge-seq", daemon=True)
        self._thread.start()

    @property
    def address(self) -> str:
        return f"{self.client}:{self.public}"

    # -------------------------------------------------- enumeration
    def ports(self) -> list[PortInfo]:
        L = lib()
        ci, pi = C.c_void_p(), C.c_void_p()
        L.snd_seq_client_info_malloc(C.byref(ci))
        L.snd_seq_port_info_malloc(C.byref(pi))
        out = []
        try:
            L.snd_seq_client_info_set_client(ci, -1)
            while L.snd_seq_query_next_client(self._seq, ci) >= 0:
                client = L.snd_seq_client_info_get_client(ci)
                cname = (L.snd_seq_client_info_get_name(ci) or b"").decode(errors="replace")
                L.snd_seq_port_info_set_client(pi, client)
                L.snd_seq_port_info_set_port(pi, -1)
                while L.snd_seq_query_next_port(self._seq, pi) >= 0:
                    out.append(PortInfo(client, L.snd_seq_port_info_get_port(pi), cname,
                                        (L.snd_seq_port_info_get_name(pi) or b"").decode(errors="replace"),
                                        L.snd_seq_port_info_get_capability(pi)))
        finally:
            L.snd_seq_client_info_free(ci)
            L.snd_seq_port_info_free(pi)
        return out

    def connect_push(self, ports: list[PortInfo]):
        L = lib()
        self._linked = list(ports)
        for p in ports:
            if p.caps & CAP_READ:
                L.snd_seq_connect_from(self._seq, self.link, p.client, p.port)
            if p.caps & CAP_WRITE:
                L.snd_seq_connect_to(self._seq, self.link, p.client, p.port)

    def disconnect_push(self):
        L = lib()
        for p in getattr(self, "_linked", []):
            if p.caps & CAP_READ:
                L.snd_seq_disconnect_from(self._seq, self.link, p.client, p.port)
            if p.caps & CAP_WRITE:
                L.snd_seq_disconnect_to(self._seq, self.link, p.client, p.port)
        self._linked = []

    # -------------------------------------------------- output
    def _send(self, port: int, msg: bytes):
        ev, keep = encode(msg)
        if ev is None:
            return
        ev.source.port = port
        with self._lock:
            lib().snd_seq_event_output_direct(self._seq, C.byref(ev))
        del keep

    def to_push(self, msg: bytes):
        self._send(self.link, msg)

    def to_apps(self, msg: bytes):
        self._send(self.public, msg)

    # -------------------------------------------------- input
    def _reader(self):
        L = lib()
        n = L.snd_seq_poll_descriptors_count(self._seq, POLLIN)
        pfds = (C.c_byte * (8 * max(1, n)))()
        L.snd_seq_poll_descriptors(self._seq, pfds, n, POLLIN)
        fds = [C.c_int.from_buffer_copy(bytes(pfds[i * 8:i * 8 + 4])).value for i in range(n)]
        poller = select.poll()
        for fd in fds:
            poller.register(fd, select.POLLIN)
        evp = C.POINTER(SeqEvent)()
        while not self._stop.is_set():
            if not poller.poll(200):
                continue
            while True:
                rc = L.snd_seq_event_input(self._seq, C.byref(evp))
                if rc < 0 or not evp:
                    break
                ev = evp.contents
                try:
                    if ev.type in (EV_CLIENT_START, EV_CLIENT_EXIT, EV_PORT_START, EV_PORT_EXIT):
                        if self.on_change:
                            self.on_change()
                    else:
                        msg = decode(ev)
                        if msg:
                            if ev.dest.port == self.link and self.on_push:
                                self.on_push(msg, ev.source.port)
                            elif ev.dest.port == self.public and self.on_app:
                                self.on_app(msg)
                except Exception:  # never let a handler kill the reader
                    traceback.print_exc()
                if L.snd_seq_event_input_pending(self._seq, 0) <= 0:
                    break

    def close(self):
        self._stop.set()
        self._thread.join(timeout=1)
        if self._seq:
            lib().snd_seq_close(self._seq)
            self._seq = C.c_void_p()


def connections_text() -> str:
    """The kernel's own view of every client, port and connection (for Health)."""
    try:
        return open("/proc/asound/seq/clients").read()
    except OSError:
        return ""
