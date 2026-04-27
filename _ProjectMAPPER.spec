# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_ProjectMAPPER\\src\\app.py'],
    pathex=['C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_ProjectMAPPER'],
    binaries=[],
    datas=[('C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_ProjectMAPPER\\assets', 'assets'), ('C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_ProjectMAPPER\\assets', 'assets'), ('C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_ProjectMAPPER\\src', 'src')],
    hiddenimports=[],
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
    a.binaries,
    a.datas,
    [],
    name='_ProjectMAPPER',
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
    icon=['C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_ProjectMAPPER\\assets\\icons\\projectmapper.ico'],
)
