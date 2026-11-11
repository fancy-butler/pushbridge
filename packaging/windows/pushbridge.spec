# -*- mode: python ; coding: utf-8 -*-
# Build:  pyinstaller packaging/windows/pushbridge.spec --noconfirm   (run from the repo root)
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

a = Analysis(
    [os.path.join(SPECPATH, "pushbridge_main.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "pushbridge", "resources", "icons"), os.path.join("pushbridge", "resources", "icons"))],
    hiddenimports=["PySide6.QtSvg", "PySide6.QtNetwork"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtPdf"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="PushBridge",
    icon=os.path.join(SPECPATH, "pushbridge.ico"),
    console=False,
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="PushBridge")
