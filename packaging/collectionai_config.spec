# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build spec for the Configuration exe — a CustomTkinter GUI
with no database/ML dependencies, so this build is small and fast
compared to the Service exe.

Build with:
    pyinstaller --noconfirm --clean packaging/collectionai_config.spec
(see scripts/build_exes.ps1 for the two-exe build script)
"""
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(ROOT / "config_app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=["customtkinter", "darkdetect"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CollectionAI-Config",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # GUI app — no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
