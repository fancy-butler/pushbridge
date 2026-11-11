# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fancy Butler
"""System tray icon, start-at-login, and single-instance handling."""
from __future__ import annotations

import getpass

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from . import theme

SOCKET_NAME = f"pushbridge-{getpass.getuser()}"

from ..platform_util import autostart_enabled, set_autostart  # noqa: E402,F401  (re-exported)


# ------------------------------------------------------------------ single instance
class SingleInstance(QObject):
    """If Push Bridge is already running, wake that one up instead of starting twice
    (two copies would fight over the controller)."""
    wake = Signal()

    def __init__(self):
        super().__init__()
        self.server = None

    def already_running(self) -> bool:
        sock = QLocalSocket()
        sock.connectToServer(SOCKET_NAME)
        if sock.waitForConnected(300):
            sock.write(b"show")
            sock.flush()
            sock.waitForBytesWritten(300)
            sock.disconnectFromServer()
            return True
        QLocalServer.removeServer(SOCKET_NAME)
        self.server = QLocalServer()
        self.server.newConnection.connect(self._on_conn)
        self.server.listen(SOCKET_NAME)
        return False

    def _on_conn(self):
        c = self.server.nextPendingConnection()
        if c:
            c.readyRead.connect(lambda: (c.readAll(), self.wake.emit()))


# ------------------------------------------------------------------ tray
class Tray(QSystemTrayIcon):
    @staticmethod
    def available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def __init__(self, win):
        super().__init__(theme.icon("pads", theme.MUTED, 64), win)
        self.win = win
        m = QMenu()
        self.status_act = QAction("Starting…", m)
        self.status_act.setEnabled(False)
        m.addAction(self.status_act)
        self.scale_act = QAction("", m)
        self.scale_act.setEnabled(False)
        m.addAction(self.scale_act)
        m.addSeparator()
        m.addAction(theme.icon("eye", theme.TEXT, 16), "Open Push Bridge", win.show_window)
        m.addAction(theme.icon("heart-pulse", theme.TEXT, 16), "Health check",
                    lambda: (win.show_window(), win.go_page(win.health_page)))
        m.addAction(theme.icon("lightbulb", theme.TEXT, 16), "Test LEDs", win.core.test_leds)
        m.addAction(theme.icon("rotate-cw", theme.TEXT, 16), "Repaint the Push", win.core.repaint_hardware)
        self.handoff_act = QAction(theme.icon("unplug", theme.TEXT, 16), "Hand the Push to Live", m)
        self.handoff_act.setCheckable(True)
        self.handoff_act.toggled.connect(lambda on: win.core.set_handoff(on) if on != win.core.engine.standby else None)
        m.addAction(self.handoff_act)
        m.addSeparator()
        m.addAction(theme.icon("power", theme.TEXT, 16), "Quit Push Bridge", win.quit_app)
        m.aboutToShow.connect(self._refresh)
        self.setContextMenu(m)
        self.activated.connect(self._activated)
        self.setToolTip("Push Bridge")
        self.show()

    def _refresh(self):
        self.handoff_act.setChecked(self.win.core.engine.standby)
        s = self.win.core.settings
        from .. import theory as T
        self.scale_act.setText(f"{T.pc_name(s['root'], s['root'])} {s['scale']}" if s["mode"] == "notes" else "Drums")

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.win.isVisible() and not self.win.isMinimized():
                self.win.hide()
            else:
                self.win.show_window()

    def set_state(self, state: str, detail: str):
        label = {"connected": "Push connected", "waiting": "Waiting for the Push",
                 "error": "Problem: open Health check", "starting": "Starting…"}.get(state, state)
        if self.win.core.demo and state == "connected":
            label = "Demo mode"
        color = {"connected": theme.ACCENT, "error": theme.BAD}.get(state, theme.MUTED)
        self.setIcon(theme.icon("pads", color, 64))
        self.status_act.setText(label)
        self.setToolTip(f"Push Bridge: {label}" + (f"\n{detail}" if detail else ""))
        prev = getattr(self, "_prev", None)
        self._prev = state
        # stay out of the way: only speak up when something is wrong
        if prev is not None and prev != state and state == "error" and not self.win.isVisible():
            self.showMessage("Push Bridge", label, theme.icon("pads", color, 32), 3000)
