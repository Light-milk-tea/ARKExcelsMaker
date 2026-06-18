# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\23625\\Desktop\\excels_maker_test\\mixed_tool1.1\\integrated_gui.py'],
    pathex=['C:\\Users\\23625\\Desktop\\excels_maker_test\\mixed_tool1.1\\pictures_get', 'C:\\Users\\23625\\Desktop\\excels_maker_test\\mixed_tool1.1\\picture_recognize'],
    binaries=[],
    datas=[('C:\\Users\\23625\\Desktop\\excels_maker_test\\mixed_tool1.1\\picture_recognize\\res', 'picture_recognize/res'), ('C:\\Users\\23625\\Desktop\\excels_maker_test\\mixed_tool1.1\\picture_recognize\\四星队名单.xlsx', 'picture_recognize'), ('C:\\Users\\23625\\.EasyOCR\\model', 'models')],
    hiddenimports=['yt_dlp', 'bili_capture', 'detect', 'gui_recognize_ops', 'easyocr', 'imageio_ffmpeg', 'cv2', 'numpy', 'PIL', 'openpyxl'],
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
    name='MixedTool',
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
    name='MixedTool',
)
