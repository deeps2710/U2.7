# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


root = Path(SPECPATH).resolve()
icon = root / "assets" / "ultron.ico"

a = Analysis(
    [str(root / "scripts" / "desktop_entry.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=[
        (str(root / "assets"), "assets"),
        (str(root / "web"), "web"),
        (str(root / "data"), "data"),
        (str(root / "ultron.config.json"), "."),
        (str(root / "ultron.config.example.json"), "."),
    ],
    hiddenimports=[
        "numpy",
        "sounddevice",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["cefpython3", "PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ULTRON 2.7",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ULTRON 2.7",
)
