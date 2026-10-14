#!/usr/bin/env bash
# ============================================================
#  PDF批量OCR工具 —— 统信 UOS / Deepin / Debian 打包脚本
# ------------------------------------------------------------
#  目标环境：统信桌面操作系统 V20
#            内核 4.19 / glibc 2.28 / GCC 8.3 / x86_64
#
#  ！核心前提：Linux 版必须在 Linux 上打包
#    · PyInstaller 不支持交叉编译，Windows 上做不出 Linux 可执行文件
#    · PyInstaller 产物依赖打包机的 glibc 版本：
#      在 glibc 2.35 的 Ubuntu 22.04 上打的包，拿到 glibc 2.28 的
#      统信 UOS 上会报 "version `GLIBC_2.29' not found"
#    ✅ 最稳的做法：就在那台统信 UOS 机器上运行本脚本
#
#  用法：
#     chmod +x build_uos.sh
#     ./build_uos.sh          打包，产出 dist/*.tar.gz
#     ./build_uos.sh --run    不打包，装好依赖后直接运行（用于快速验证）
# ============================================================

set -euo pipefail

cd "$(dirname "$0")"

APP_NAME="PDF批量OCR工具"
VERSION="1.5.0"
VENV_DIR=".venv-uos"
RUN_ONLY=0

if [ "${1:-}" = "--run" ]; then
    RUN_ONLY=1
fi

say()  { printf '\033[1;36m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$1"; }
die()  { printf '\033[1;31m[x] %s\033[0m\n' "$1" >&2; exit 1; }

echo
echo "  PDF批量OCR工具 Linux/UOS 打包  (v${VERSION})"
echo "  架构：$(uname -m)"
if [ -r /etc/os-release ]; then
    echo "  系统：$(. /etc/os-release; echo "${PRETTY_NAME:-unknown}")"
fi
echo

# ------------------------------------------------------------ 环境兼容性检查
GLIBC_VER="$(ldd --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+$' || true)"
if [ -n "$GLIBC_VER" ]; then
    echo "  glibc：${GLIBC_VER}"
    NEWER="$(printf '%s\n%s\n' "2.28" "$GLIBC_VER" | sort -V | tail -1)"
    if [ "$NEWER" != "2.28" ]; then
        warn "本机 glibc 高于统信 UOS V20 的 2.28。
     产出的程序在 UOS 上可能报 GLIBC_2.29 / GLIBC_2.34 之类的符号缺失错误。
     如需给 UOS V20 分发，请直接在那台 UOS 机器上打包。"
    fi
else
    warn "无法识别 glibc 版本，跳过兼容性检查。"
fi
echo

# ------------------------------------------------------------ 1. Python
say "1/6 检查 Python 与 tkinter"

PY="$(command -v python3)" || die "未找到 python3，请先安装：sudo apt install -y python3 python3-pip python3-tk"
echo "    使用：$PY  ($("$PY" -V 2>&1))"

PY_VER="$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
case "$PY_VER" in
    3.6|3.7|3.8|3.9|3.10|3.11|3.12|3.13|3.14) ;;
    *) die "不支持的 Python 版本：$PY_VER" ;;
esac

if ! "$PY" -c "import tkinter" >/dev/null 2>&1; then
    die "当前 Python 缺少 tkinter，这是本工具的图形界面必需的。
    请执行（需要 sudo）：
        sudo apt install -y python3-tk
    装完再重新运行本脚本。"
fi
echo "    tkinter：$("$PY" -c 'import tkinter;print(tkinter.TkVersion)')"
echo "    Python：$PY_VER"

# ------------------------------------------------------------ 2. 虚拟环境
say "2/6 准备虚拟环境（$VENV_DIR）"
if [ ! -x "$VENV_DIR/bin/python" ]; then
    if ! "$PY" -m venv "$VENV_DIR" 2>/dev/null; then
        die "创建虚拟环境失败，通常是缺少 python3-venv。请执行：
        sudo apt install -y python3-venv python3-pip python3-tk"
    fi
fi
VENV_PY="$VENV_DIR/bin/python"
echo "    $("$VENV_PY" -V 2>&1)"

# ------------------------------------------------------------ 3. 依赖
say "3/6 安装依赖（首次较慢）"
# 内网环境可先设置 PIP_INDEX，例如：
#   export PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
PIP_ARGS=()
if [ -n "${PIP_INDEX:-}" ]; then
    PIP_ARGS=(-i "$PIP_INDEX")
    echo "    使用镜像源：$PIP_INDEX"
fi

"$VENV_PY" -m pip install -q --upgrade pip "${PIP_ARGS[@]}"
"$VENV_PY" -m pip install -r requirements_uos.txt "${PIP_ARGS[@]}"

if ! "$VENV_PY" -c "import tkinter" >/dev/null 2>&1; then
    die "虚拟环境里的 tkinter 不可用，请确认已安装 python3-tk。"
fi

# ------------------------------------------------------------ 4. 直接运行模式
if [ "$RUN_ONLY" -eq 1 ]; then
    say "4/6 --run 模式：直接启动程序（不打包）"
    exec "$VENV_PY" run_pipeline_gui.py
fi

# ------------------------------------------------------------ 5. 打包
say "5/6 执行 PyInstaller 打包"
echo "    输出方式：onedir（比单文件更稳，避免 /tmp 挂载 noexec 导致启动失败）"

"$VENV_PY" -m PyInstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name "$APP_NAME" \
    --add-data "mineru_icon.png:." \
    --collect-data docx \
    --exclude-module pytest \
    --exclude-module unittest \
    --exclude-module pydoc \
    run_pipeline_gui.py

APP_DIR="dist/$APP_NAME"
if [ ! -x "$APP_DIR/$APP_NAME" ]; then
    die "打包失败：没有生成 $APP_DIR/$APP_NAME"
fi

# ------------------------------------------------------------ 6. 组装分发包
say "6/6 组装分发包"

# 启动器（UOS 文件管理器里可双击）
cat > "$APP_DIR/启动.sh" <<'LAUNCHER'
#!/usr/bin/env bash
cd "$(dirname "$0")"
exec "./PDF批量OCR工具" "$@"
LAUNCHER
chmod +x "$APP_DIR/启动.sh"

# 桌面快捷方式（用当前构建目录的绝对路径，移动位置后需自行修改 Exec/Icon）
INSTALL_DIR="$(cd "$APP_DIR" && pwd)"
ICON_PATH="$INSTALL_DIR/_internal/mineru_icon.png"
[ -f "$ICON_PATH" ] || ICON_PATH="$INSTALL_DIR/mineru_icon.png"

cat > "$APP_DIR/${APP_NAME}.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=${APP_NAME}
Name[zh_CN]=${APP_NAME}
Comment=PDF 批量 OCR 识别与转换工具
Exec=${INSTALL_DIR}/${APP_NAME}
Icon=${ICON_PATH}
Terminal=false
Categories=Office;Utility;
DESKTOP
chmod +x "$APP_DIR/${APP_NAME}.desktop"

TARBALL="dist/${APP_NAME}-uos-$(uname -m)-v${VERSION}.tar.gz"
rm -f "$TARBALL"
tar -czf "$TARBALL" -C dist "$APP_NAME"

APP_SIZE="$(du -sh "$APP_DIR" | cut -f1)"
TAR_SIZE="$(du -h "$TARBALL" | cut -f1)"

cat <<EOF

============================================================
 打包完成

   程序目录   : $APP_DIR   ($APP_SIZE)
   分发压缩包 : $TARBALL   ($TAR_SIZE)

 分发给同事的用法
 ------------------------------------------------------------
 1. 把这个 tar.gz 发过去，对方解压（统信自带归档管理器可双击解压）
 2. 进入解压出的目录，双击「启动.sh」
    若提示无执行权限（U 盘/FAT 传输会丢权限位），执行：
        chmod +x 启动.sh "${APP_NAME}" && ./启动.sh
 3. 想加桌面图标：把 ${APP_NAME}.desktop 复制到
        ~/.local/share/applications/
    再在「启动器」里搜索 ${APP_NAME} 即可。
        注意：desktop 里写死了当前路径 $INSTALL_DIR
        如果移动了程序目录，需要同步修改 Exec 和 Icon 两行。

 常见问题
 ------------------------------------------------------------
 · 双击没反应：改在终端里运行 ./启动.sh，就能看到报错信息
 · 提示 GLIBC 版本缺失：打包机与目标机 glibc 不匹配，
   请在目标 UOS 机器上重新执行本脚本
 · 统信「安全中心」拦截：在安全中心里把该程序加入信任/白名单
============================================================
EOF
