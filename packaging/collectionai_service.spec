# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build spec for the Scheduler Service exe. Pulls in the full
pipeline (XGBoost, SHAP, Polars, MLflow, Oracle) plus pywin32's service
framework and APScheduler, so this build is considerably heavier and
slower than the Configuration exe's.

Bundles two read-only resources the pipeline loads by relative path at
runtime (see src/core/paths.resource_path): the SQL feature files and the
LLM system prompt markdown. Everything under models/, data/cache/,
logs/, mlruns/, .env and schedule.json is mutable app state and lives
outside the bundle entirely — see src/core/paths.py.

Build with:
    pyinstaller --noconfirm --clean packaging/collectionai_service.spec
(see scripts/build_exes.ps1 for the two-exe build script)
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH).resolve().parent

datas = [
    (str(ROOT / "src" / "database" / "features"), "src/database/features"),
    (str(ROOT / "src" / "explainability" / "llm_system_prompt.md"), "src/explainability"),
]

binaries = []

# XGBoost ships its actual prediction engine as a freestanding native
# library (xgboost/lib/xgboost.dll) that it loads itself via ctypes at
# import time (xgboost/libpath.py), searching a fixed list of relative
# paths. PyInstaller's static import scanner never sees that ctypes
# lookup, so the DLL is silently left out of the bundle and every run
# fails at "import xgboost" with XGBoostLibraryNotFound — there is no
# community hook for it (checked _pyinstaller_hooks_contrib), so it has
# to be collected explicitly here. collect_dynamic_libs() finds the DLL
# and places it back at the same xgboost/lib/ path the loader expects;
# collect_data_files() grabs xgboost/VERSION, which the package also
# reads at import time.
binaries += collect_dynamic_libs("xgboost")
datas += collect_data_files("xgboost")

hiddenimports = [
    "win32timezone",           # pywin32 service framework needs this at runtime
    "apscheduler.triggers.cron",
    "apscheduler.executors.pool",
    "apscheduler.jobstores.memory",
    "sklearn.utils._typedefs",
    "sklearn.neighbors._partition_nodes",
]

a = Analysis(
    [str(ROOT / "service_app.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="CollectionAI-Service",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,          # pywin32 CLI verbs (install/start/stop/debug) print here
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
