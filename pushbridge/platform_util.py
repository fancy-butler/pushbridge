# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fancy Butler
"""The few places Linux and Windows differ outside of MIDI."""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

IS_WIN = sys.platform == "win32"
FROZEN = getattr(sys, "frozen", False)      # PyInstaller build


def config_dir() -> Path:
    if IS_WIN:
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "PushBridge"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "pushbridge"


def launch_command() -> str:
    if FROZEN:
        return f'"{sys.executable}" --minimized'
    exe = shutil.which("pushbridge")
    if exe:
        return f'"{exe}" --minimized' if IS_WIN else f"{exe} --minimized"
    py = sys.executable
    if IS_WIN and py.lower().endswith("python.exe"):
        py = py[:-10] + "pythonw.exe"   # no console window
    return f'"{py}" -m pushbridge --minimized' if IS_WIN else f"{py} -m pushbridge --minimized"


# ------------------------------------------------------------------ start at login
_AUTOSTART_LINUX = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / "pushbridge.desktop"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_enabled() -> bool:
    if IS_WIN:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
                winreg.QueryValueEx(k, "PushBridge")
                return True
        except OSError:
            return False
    return _AUTOSTART_LINUX.exists()


def set_autostart(on: bool):
    if IS_WIN:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, "PushBridge", 0, winreg.REG_SZ, launch_command())
            else:
                try:
                    winreg.DeleteValue(k, "PushBridge")
                except OSError:
                    pass
        return
    if on:
        _AUTOSTART_LINUX.parent.mkdir(parents=True, exist_ok=True)
        _AUTOSTART_LINUX.write_text(
            "[Desktop Entry]\nType=Application\nName=Push Bridge\nComment=Ableton Push 1 front end\n"
            f"Exec={launch_command()}\nIcon=pushbridge\nTerminal=false\n"
            "X-GNOME-Autostart-enabled=true\nX-KDE-autostart-after=panel\n")
    else:
        try:
            _AUTOSTART_LINUX.unlink()
        except FileNotFoundError:
            pass


# ------------------------------------------------------------------ is Ableton Live running?
LIVE_EXE = re.compile(r"^ableton live.*\.exe$", re.I)


def windows_processes() -> list[str]:
    import ctypes as C
    from ctypes import wintypes as W

    class PROCESSENTRY32W(C.Structure):
        _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD),
                    ("th32DefaultHeapID", C.c_size_t), ("th32ModuleID", W.DWORD), ("cntThreads", W.DWORD),
                    ("th32ParentProcessID", W.DWORD), ("pcPriClassBase", C.c_long), ("dwFlags", W.DWORD),
                    ("szExeFile", C.c_wchar * 260)]

    k32 = C.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = C.c_void_p
    k32.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
    k32.Process32FirstW.argtypes = [C.c_void_p, C.POINTER(PROCESSENTRY32W)]
    k32.Process32NextW.argtypes = [C.c_void_p, C.POINTER(PROCESSENTRY32W)]
    k32.CloseHandle.argtypes = [C.c_void_p]
    snap = k32.CreateToolhelp32Snapshot(2, 0)       # TH32CS_SNAPPROCESS
    if not snap or snap == C.c_void_p(-1).value:
        return []
    names = []
    try:
        e = PROCESSENTRY32W()
        e.dwSize = C.sizeof(e)
        ok = k32.Process32FirstW(snap, C.byref(e))
        while ok:
            names.append(e.szExeFile)
            ok = k32.Process32NextW(snap, C.byref(e))
    finally:
        k32.CloseHandle(snap)
    return names


def live_running() -> list[str]:
    """Names of running Ableton Live executables (Windows)."""
    if not IS_WIN:
        return []
    try:
        return sorted({n for n in windows_processes() if LIVE_EXE.match(n)})
    except Exception:
        return []
