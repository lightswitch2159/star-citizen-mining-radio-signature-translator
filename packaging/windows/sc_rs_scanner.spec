# PyInstaller spec for SC RS Scanner (Windows build).
#
# Produces a self-contained folder ("dist/SC RS Scanner/") with the app,
# Python runtime, all pip dependencies, and a bundled portable Tesseract
# copy -- end users need nothing pre-installed.
#
# Run via build.bat, not directly, so the tesseract_bundle/ folder gets
# validated first with a clear error if it's missing.

import os

block_cipher = None
here = os.path.dirname(os.path.abspath(SPEC))
project_root = os.path.abspath(os.path.join(here, "..", ".."))
tesseract_bundle_dir = os.path.join(here, "tesseract_bundle")

datas = []
if os.path.isdir(tesseract_bundle_dir):
    datas.append((tesseract_bundle_dir, "tesseract_bundle"))

a = Analysis(
    [os.path.join(project_root, "main.py")],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # pynput picks its backend at import time based on platform;
        # PyInstaller's static analysis can miss the Windows one.
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SC RS Scanner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # no terminal window -- this is a GUI app
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # add icon=os.path.join(here, "icon.ico") once you have one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SC RS Scanner",
)
