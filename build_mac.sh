#!/usr/bin/env bash
# ============================================================
#  PDF批量OCR工具 —— macOS 一键打包脚本
# ------------------------------------------------------------
#  用法：把整个项目文件夹拷到 Mac 上，然后在「终端」里执行：
#      cd 项目文件夹
#      chmod +x build_mac.sh
#      ./build_mac.sh
#
#  产物：dist/PDF批量OCR工具.app（可直接双击运行）
#        dist/PDF批量OCR工具-macOS-<架构>-v1.5.0.zip（分发用）
#
#  说明：PyInstaller 不支持交叉编译，macOS 的包只能在 macOS 上打。
# ============================================================

set -euo pipefail

cd "$(dirname "$0")"

APP_NAME="PDF批量OCR工具"
VERSION="1.5.0"
VENV_DIR=".venv-mac"
ICONSET="mineru_icon.iconset"
ICNS="mineru_icon.icns"

say()  { printf '\033[1;36m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$1"; }
die()  { printf '\033[1;31m[x] %s\033[0m\n' "$1" >&2; exit 1; }

echo
echo "  PDF批量OCR工具 macOS 打包  (v${VERSION})"
echo "  当前机器架构：$(uname -m)  系统：$(sw_vers -productVersion 2>/dev/null || echo 'unknown')"
echo

# ------------------------------------------------------------ 1. Python + tkinter
say "1/6 检查 Python 与 tkinter"

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
    for c in python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$c" >/dev/null 2>&1; then PYTHON_BIN="$(command -v "$c")"; break; fi
    done
fi

if [ -z "$PYTHON_BIN" ]; then
    die "未找到 python3。请先安装官方 Python：
    https://www.python.org/downloads/macos/  （推荐 3.12 或 3.13）"
fi

echo "    使用：$PYTHON_BIN  ($("$PYTHON_BIN" -V 2>&1))"

if ! "$PYTHON_BIN" -c "import tkinter" >/dev/null 2>&1; then
    die "当前 Python 不带 tkinter，无法打包图形界面程序。
    解决办法（任选其一）：
      · 推荐：安装 python.org 官方 Python 3.12 / 3.13（自带 Tk/Tcl）
      · Homebrew：brew install python-tk
    注意：macOS 自带的 /usr/bin/python3 不含 tkinter，不能用于打包。"
fi

echo "    tkinter：$("$PYTHON_BIN" -c 'import tkinter;print(tkinter.TkVersion)')"

# ------------------------------------------------------------ 2. 虚拟环境
say "2/6 准备打包环境（$VENV_DIR）"
if [ ! -x "$VENV_DIR/bin/python" ]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
VENV_PY="$VENV_DIR/bin/python"

# ------------------------------------------------------------ 3. 依赖
say "3/6 安装依赖（首次执行会慢一些）"
"$VENV_PY" -m pip install -q --upgrade pip
"$VENV_PY" -m pip install -q pyinstaller requests PyPDF2 python-docx pillow

if ! "$VENV_PY" -c "import tkinter" >/dev/null 2>&1; then
    warn "虚拟环境中的 tkinter 不可用，打包大概率会失败，请检查上面的安装建议。"
fi

# ------------------------------------------------------------ 4. 图标 .icns
say "4/6 生成 macOS 图标（.icns）"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"

"$VENV_PY" - "$ICONSET" <<'PY'
import sys
from PIL import Image

out = sys.argv[1]
with Image.open("mineru_icon.png") as im:
    src = im.convert("RGBA")

if src.width < 512:
    print(f"[!] 源图 mineru_icon.png 只有 {src.width}x{src.height}，"
          f"放大后图标会偏糊。建议换一张 1024x1024 的 PNG。")

# iconset 标准规格：基础尺寸 + 对应的 @2x
for base, retina in ((16, 32), (32, 64), (128, 256), (256, 512), (512, 1024)):
    for size, suffix in ((base, ""), (retina, "@2x")):
        src.resize((size, size), Image.LANCZOS).save(
            f"{out}/icon_{base}x{base}{suffix}.png"
        )
print("[ok] iconset 生成完毕")
PY

if ! iconutil -c icns "$ICONSET" -o "$ICNS"; then
    die "iconutil 生成 .icns 失败。"
fi
rm -rf "$ICONSET"

# ------------------------------------------------------------ 5. 打包
say "5/6 执行 PyInstaller 打包"
if [ -n "${PYI_TARGET_ARCH:-}" ]; then
    echo "    目标架构：$PYI_TARGET_ARCH"
fi

"$VENV_PY" -m PyInstaller --noconfirm --clean --log-level WARN run_pipeline_gui_mac.spec

APP_PATH="dist/${APP_NAME}.app"
if [ ! -d "$APP_PATH" ]; then
    die "打包失败：没有生成 $APP_PATH"
fi

# ------------------------------------------------------------ 6. 分发压缩包
say "6/6 生成分发包"
ARCH="$(uname -m)"
ZIP="dist/${APP_NAME}-macOS-${ARCH}-v${VERSION}.zip"
rm -f "$ZIP"
ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$ZIP"

SIZE="$(du -h "$ZIP" | cut -f1)"
APP_SIZE="$(du -sh "$APP_PATH" | cut -f1)"

cat <<EOF

============================================================
 打包完成

   应用程序   : $APP_PATH   ($APP_SIZE)
   分发压缩包 : $ZIP   ($SIZE)

 分发给别人时的注意事项
 -----------------------------------------------------------
 1. 本包未做 Apple 代码签名与公证，对方首次打开会被 Gatekeeper
    拦截。两种放行方式：
      方式一：在 Finder 里右键点 .app → 选「打开」→ 弹窗里再点「打开」
      方式二：终端执行
          xattr -dr com.apple.quarantine "/路径/${APP_NAME}.app"
 2. 架构匹配：本机是 $(uname -m)，产物只能给 $(uname -m) 的 Mac 用
    （Apple Silicon 的产物无法在 Intel Mac 上运行）。
    需要同时兼容 Intel 与 Apple Silicon 时，改用通用二进制重打：
          PYI_TARGET_ARCH=universal2 ./build_mac.sh
============================================================
EOF
