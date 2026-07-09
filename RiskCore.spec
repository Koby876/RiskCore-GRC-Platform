# -*- mode: python ; coding: utf-8 -*-
#
# RiskCore GRC Platform v1.5 — PyInstaller Spec File
#
# HOW TO BUILD:
#   1. Open a terminal in your RiskCore folder
#   2. Run:  py -m PyInstaller RiskCore.spec
#   3. Your exe will be in:  dist\RiskCore\RiskCore.exe
#
# NOTE: Do NOT use the long command-line build — use this spec file.
# It handles all paths, hidden imports, and assets automatically.

import os
import sys
from pathlib import Path

# ── Root of the project (where this spec file lives) ─────────────────────────
ROOT = os.path.dirname(os.path.abspath(SPEC))

# ── Collect all data folders ──────────────────────────────────────────────────
datas = [
    # (source_path,  destination_in_bundle)
    (os.path.join(ROOT, 'assets'),  'assets'),
    (os.path.join(ROOT, 'core'),    'core'),
    (os.path.join(ROOT, 'ui'),      'ui'),
    (os.path.join(ROOT, 'widgets'), 'widgets'),
    (os.path.join(ROOT, 'data'),    'data'),
]

# ── Hidden imports PyInstaller misses ─────────────────────────────────────────
hiddenimports = [
    # PySide6 extras
    'PySide6.QtXml',
    'PySide6.QtPrintSupport',
    'PySide6.QtSvg',
    'PySide6.QtNetwork',
    # PDF generation
    'reportlab',
    'reportlab.graphics',
    'reportlab.platypus',
    'reportlab.lib',
    'reportlab.pdfgen',
    # PIL/Pillow — required by reportlab for image handling
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    'pillow',
    # Excel
    'openpyxl',
    'openpyxl.styles',
    'openpyxl.utils',
    # Auth
    'bcrypt',
    '_bcrypt',
    # Encryption
    'cryptography',
    'cryptography.fernet',
    'cryptography.hazmat.primitives',
    'cryptography.hazmat.backends',
    # PDF reading
    'pypdf',
    # Standard
    'sqlite3',
    'json',
    'csv',
    'zipfile',
    'platform',
    'subprocess',
    'urllib.request',
    'urllib.error',
]

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    [os.path.join(ROOT, 'main.py')],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Things we definitely don't need — keeps the exe smaller
        'tkinter',
        'customtkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'IPython',
        'jupyter',
        'notebook',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,      # bundled into single exe (onefile)
    a.datas,         # bundled into single exe (onefile)
    [],
    name='RiskCore',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # No console window — clean desktop app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Icon — shown in Explorer, taskbar, and title bar
    icon=os.path.join(ROOT, 'assets', 'images', 'riskcore_logo.png'),
    version_file=None,
)
# NOTE: No COLLECT block — onefile mode bundles everything into RiskCore.exe
# Users double-click RiskCore.exe — no folder needed beside it
# riskcore.db, riskcore.key etc are stored next to the exe (not inside it)
