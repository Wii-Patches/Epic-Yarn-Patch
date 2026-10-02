# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

ICON = os.path.join(SPECPATH, 'assets', 'icon.icns' if os.uname().sysname == 'Darwin' else 'icon.ico')

# tkinterdnd2 ships per-platform tkdnd Tcl binaries that must come along, or
# the frozen app silently loses drag-and-drop and falls back to click-to-browse.
dnd_datas, dnd_binaries, dnd_hidden = collect_all('tkinterdnd2')

# wit is bundled when it is on PATH at build time (or WIT=/path/to/wit)
wit = os.environ.get('WIT') or __import__('shutil').which('wit')
wit_bins = [(wit, '.')] if wit else []
if wit and wit.lower().endswith('.exe'):        # the Cygwin build needs its runtime DLLs next to it
    wd = os.path.dirname(wit)
    wit_bins += [(os.path.join(wd, f), '.') for f in os.listdir(wd) if f.lower().endswith('.dll')]

a = Analysis(
    ['gui.py'],
    pathex=[SPECPATH],
    binaries=dnd_binaries + wit_bins,
    datas=dnd_datas + [(os.path.join(SPECPATH, 'patches.json'), '.'),
                       (os.path.join(SPECPATH, 'assets', 'icon.png'), 'assets')],
    hiddenimports=dnd_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Kirby-Patcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=os.environ.get('TARGET_ARCH') or None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Kirby-Patcher',
)
app = BUNDLE(
    coll,
    name='Kirby-Patcher.app',
    icon=ICON,
    bundle_identifier='net.quatric.kirby-patcher',
)
