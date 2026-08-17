# PyInstaller spec file — produces a single-file .exe with no internet needed.
#
# Build:
#   pip install pyinstaller
#   pyinstaller llr.spec
#
# Output: dist/llr.exe  (Windows) or dist/llr  (Linux/Mac)

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ["llr/cli.py"],
    pathex=[str(Path(".").resolve())],
    binaries=[],
    datas=[
        ("rules.yaml", "."),                        # bundle rules.yaml next to the exe
        ("docs/fpwin_reference.md", "docs"),        # instruction reference for --deep
    ],
    hiddenimports=[
        "llr.rules.builtin",          # dynamically imported by engine
        "llr.web",
        "anthropic",
        "yaml",
        "click",
        "rich",
        "flask",
        "werkzeug",
        "jinja2",
        "itsdangerous",
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="llr",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
