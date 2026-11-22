# -*- mode: python ; coding: utf-8 -*-
# build gublan studio itself:  py -m PyInstaller --noconfirm GublanStudio.spec
from PyInstaller.utils.hooks import collect_all, collect_submodules

# gublancore.py also ships as a plain file: exported games are built from it (see studio/exporter.py core_folder)
datas = [('docs', 'docs'), ('gublancore.py', '.')]
binaries = []
hiddenimports = ['gublancore', 'gublanconvert'] + collect_submodules('studio')
tmp_ret = collect_all('OpenGL')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['gublanide.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'matplotlib', 'IPython', 'pytest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='GublanStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
