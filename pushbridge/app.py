# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fancy Butler
"""Entry point: `pushbridge` (GUI), `pushbridge --headless` (background service)."""
from __future__ import annotations

import argparse
import signal
import sys
import threading

from . import __version__


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pushbridge", description="Ableton Push 1 front end for Linux")
    ap.add_argument("--demo", action="store_true", help="no hardware: play the on-screen Push")
    ap.add_argument("--headless", action="store_true", help="run without a window (for a systemd user service)")
    ap.add_argument("--minimized", action="store_true", help="start hidden in the system tray")
    ap.add_argument("--screenshot", help=argparse.SUPPRESS)
    ap.add_argument("--page", type=int, default=0, help=argparse.SUPPRESS)
    ap.add_argument("--version", action="version", version=f"Push Bridge {__version__}")
    args = ap.parse_args(argv)

    if not args.headless:
        from PySide6.QtWidgets import QApplication
        app = QApplication(sys.argv[:1])
        from .ui.tray import SingleInstance
        single = SingleInstance()
        if not args.screenshot and single.already_running():
            print("Push Bridge is already running; showing it.")
            return 0

    from .core import Core
    core = Core(demo=args.demo)

    if args.headless:
        core.status_listeners.append(lambda st, d: print(f"[pushbridge] {st}: {d}", flush=True))
        if core.midi_error:
            print(f"[pushbridge] MIDI unavailable: {core.midi_error}", file=sys.stderr)
        elif core.seq:
            print(f"[pushbridge] MIDI port Push Bridge:Push 1 at {core.seq.address}", flush=True)
        done = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: done.set())
        signal.signal(signal.SIGTERM, lambda *_: done.set())
        core.start()
        done.wait()
        core.stop()
        return 0

    from PySide6.QtCore import QTimer
    from .ui import theme
    from .ui.mainwindow import MainWindow

    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Push Bridge")
    app.setDesktopFileName("pushbridge")
    app.setStyle("Fusion")
    app.setStyleSheet(theme.QSS)
    win = MainWindow(core)
    single.wake.connect(win.show_window)
    if not (args.minimized and win.tray):
        win.show()
    core.start()
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    if args.screenshot:
        win.go(args.page)
        def shoot():
            win.grab().save(args.screenshot)
            app.quit()
        QTimer.singleShot(1500, shoot)
    rc = app.exec()
    core.stop()
    return rc
