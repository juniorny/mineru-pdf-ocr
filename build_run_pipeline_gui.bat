@echo off
REM ============================================================
REM  PDF批量OCR工具 - 打包脚本
REM  使用系统 Python 3.14 独立 venv（含 tkinter），避免 Anaconda
REM  环境导致 exe 体积膨胀；WorkBuddy 托管 Python 无 tkinter，勿用。
REM ============================================================
set "BASE_PY=C:\Python314\python.exe"
set "VENV=%USERPROFILE%\.workbuddy\binaries\python\envs\mineru_pack314"
set "PY=%VENV%\Scripts\python.exe"

if not exist "%PY%" (
    echo [1/4] 创建独立打包环境...
    "%BASE_PY%" -m venv "%VENV%"
)

echo [2/4] 安装依赖...
"%PY%" -m pip install -q --upgrade pip
"%PY%" -m pip install -q pyinstaller requests PyPDF2 python-docx pillow

echo [3/4] 生成图标...
"%PY%" -c "from PIL import Image; Image.open('mineru_icon.png').save('mineru_icon.ico', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"

echo [4/4] 打包...
"%PY%" -m PyInstaller --noconfirm --clean --log-level WARN run_pipeline_gui.spec

if exist dist\run_pipeline_gui.exe (
    echo.
    echo 打包成功: dist\run_pipeline_gui.exe
) else (
    echo.
    echo 打包失败，请检查上方输出。
)
pause
