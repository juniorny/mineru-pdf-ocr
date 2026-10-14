# -*- mode: python ; coding: utf-8 -*-
"""
macOS 打包配置 —— PDF批量OCR工具
================================================================
用法（必须在 macOS 上执行，PyInstaller 不支持交叉编译）：

    python3 -m PyInstaller --noconfirm --clean run_pipeline_gui_mac.spec

产出：dist/PDF批量OCR工具.app

如需 Intel + Apple Silicon 通用二进制，先设置环境变量：
    PYI_TARGET_ARCH=universal2 python3 -m PyInstaller ... run_pipeline_gui_mac.spec

（推荐直接跑 build_mac.sh，它会自动完成 venv / 依赖 / 图标 / 打包全流程。）
"""

import os

from PyInstaller.utils.hooks import collect_data_files

APP_NAME = "PDF批量OCR工具"
APP_VERSION = "1.5.0"
BUNDLE_ID = "cn.csg.audit.pdfocr"

# universal2 = Intel + Apple Silicon 通用；留空则跟随当前机器架构
TARGET_ARCH = os.environ.get("PYI_TARGET_ARCH") or None


a = Analysis(
    ["run_pipeline_gui.py"],
    pathex=[],
    binaries=[],
    # mineru_icon.png 是窗口图标，运行时由 tk.PhotoImage 读取，必须一并打包
    datas=[("mineru_icon.png", ".")] + collect_data_files("docx"),
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 注意：不要在这里排除 'distutils'，PyInstaller 的 hook-distutils 会与之冲突并直接报错
    excludes=["unittest", "pytest", "tkinter.test", "pydoc"],
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
    # 可执行文件名保持 ASCII，中文名交给 BUNDLE 的显示名
    name="PDFOCR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=TARGET_ARCH,
    codesign_identity=None,
    entitlements_file=None,
    icon="mineru_icon.icns",
)

app = BUNDLE(
    exe,
    name=f"{APP_NAME}.app",
    icon="mineru_icon.icns",
    bundle_identifier=BUNDLE_ID,
    version=APP_VERSION,
    info_plist={
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleName": APP_NAME,
        # 让 Tk 使用现代外观，并支持 Retina 高清屏
        "NSRequiresAquaSystemAppearance": False,
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "10.15",
        "LSApplicationCategoryType": "public.app-category.productivity",
    },
)
