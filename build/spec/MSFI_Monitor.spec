# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['E:\\SoftwareProjects\\Superannuation_Income_Monitor\\msfi_app\\windows_launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('E:\\SoftwareProjects\\Superannuation_Income_Monitor\\msfi_app\\templates', 'templates'), ('E:\\SoftwareProjects\\Superannuation_Income_Monitor\\msfi_app\\static', 'static')],
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
    [],
    exclude_binaries=True,
    name='MSFI_Monitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MSFI_Monitor',
)
