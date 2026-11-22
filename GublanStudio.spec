# -*- mode: python ; coding: utf-8 -*-
# build gublan studio itself with build.ps1 (or:  py -m PyInstaller --noconfirm GublanStudio.spec)
import os
import re

from PyInstaller.utils.hooks import collect_all, collect_submodules
from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

# the exe's file version comes from studio/version.py, so windows shows the same number the program does
with open(os.path.join(SPECPATH, 'studio', 'version.py'), encoding='utf-8') as handle:
    VERSION = re.search(r'^VERSION\s*=\s*"([0-9.]+)"', handle.read(), re.M).group(1)
_parts = (tuple(int(part) for part in VERSION.split('.')) + (0, 0, 0, 0))[:4]
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_parts, prodvers=_parts, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                      subtype=0x0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable('040904B0', [
            StringStruct('CompanyName', 'Gublan'),
            StringStruct('FileDescription', 'Gublan Studio'),
            StringStruct('FileVersion', VERSION),
            StringStruct('InternalName', 'GublanStudio'),
            StringStruct('OriginalFilename', 'GublanStudio.exe'),
            StringStruct('ProductName', 'Gublan Studio'),
            StringStruct('ProductVersion', VERSION),
        ])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])]),
    ],
)

# gublancore.py and gublanpresence.py also ship as plain files: exported games are built from them
# (see studio/exporter.py core_folder). runtimes/ holds the python, javascript and lua runtimes that
# "export as another language" copies next to a translated program, and modules/ the modules `use` finds.
datas = [('docs', 'docs'), ('gublancore.py', '.'), ('gublanpresence.py', '.'), ('logo.png', '.'),
         ('logo.ico', '.'), ('runtimes', 'runtimes'), ('modules', 'modules')]
binaries = []
hiddenimports = (['gublancore', 'gublanconvert', 'gublanpresence', 'gublantranslate', 'gublanmcp']
                 + collect_submodules('studio'))
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
    icon='logo.ico',
    version=version_info,
)
