# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

# Collect all binary dependencies from coincurve
coincurve_binaries = collect_dynamic_libs('coincurve')
coincurve_datas = collect_data_files('coincurve')

# Collect protobuf schema files
schema_datas = collect_data_files('lbry.schema')

# Collect certifi certificates
certifi_datas = collect_data_files('certifi')

# Combine all binaries and datas
all_binaries = coincurve_binaries
all_datas = coincurve_datas + schema_datas + certifi_datas

a = Analysis(
    ['lbry\\extras\\cli.py'],
    pathex=[],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=[
        'coincurve',
        'coincurve._libsecp256k1',
        'lbry.schema.claim',
        'pkg_resources.py2_warn',
    ],
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
    name='lbrynet',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
