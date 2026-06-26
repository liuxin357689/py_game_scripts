# ============================================
# Hero AFK - PyInstaller 打包配置
# ============================================
# 使用方法:
#   cd projects/hero-afk
#   pyinstaller build.spec
# ============================================

# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main.py'],
    pathex=['../..'],  # game_scripts 根目录，用于查找 game_platform 包
    binaries=[],
    datas=[
        ('config.yaml', '.'),
        ('hero_afk/templates', 'hero_afk/templates'),
    ],
    hiddenimports=[
        'hero_afk',
        'hero_afk.tasks',
        'hero_afk.gui',
        'hero_afk._paths',
        'game_platform',
        'game_platform.adb',
        'game_platform.adb.device',
        'game_platform.adb.scanner',
        # game_platform.ocr 需要 PaddleOCR，已排除
        'game_platform.task',
        'game_platform.task.base_task',
        'game_platform.gui',
        'game_platform.gui.main_window',
        'game_platform.gui.control_panel',
        'game_platform.gui.log_viewer',
        'game_platform.gui.device_manager',
        'game_platform.screenshot',
        'PyQt6',
        'adb_shell',
        'cv2',
        'yaml',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # PaddlePaddle + PaddleOCR（~60MB+）
        # 当前项目使用像素颜色检测方案，不需要 OCR
        'paddle',
        'paddleocr',
        'ppocr',
        # 测试和开发模块
        'pytest',
        'unittest',
        'setuptools',
        'pip',
        'distutils',
        'tkinter',
        '_tkinter',
        # 不需要的 Qt 模块
        'PyQt6.QtWebEngine',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtMultimedia',
        'PyQt6.QtMultimediaWidgets',
        'PyQt6.QtBluetooth',
        'PyQt6.QtNetworkAuth',
        'PyQt6.QtNfc',
        'PyQt6.QtPositioning',
        'PyQt6.QtRemoteObjects',
        'PyQt6.QtSensors',
        'PyQt6.QtSerialPort',
        'PyQt6.QtWebChannel',
        'PyQt6.QtWebSockets',
        'PyQt6.QtQuick',
        'PyQt6.QtQuick3D',
        'PyQt6.QtQuickWidgets',
        'PyQt6.QtQml',
        'PyQt6.Qt3DCore',
        'PyQt6.Qt3DRender',
        'PyQt6.Qt3DInput',
        'PyQt6.Qt3DLogic',
        'PyQt6.Qt3DAnimation',
        'PyQt6.Qt3DExtras',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='HeroAFK',
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
