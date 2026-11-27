@echo off
chcp 65001 >nul
setlocal

echo ============================================================
echo  AnyBar 打包脚本
echo ============================================================
echo.

cd /d "%~dp0"

rem 优先级：ANYBAR_PYTHON 环境变量 > 当前激活的 Conda/Venv > PATH 中的 python
set "PYTHON=%ANYBAR_PYTHON%"
if not defined PYTHON if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" set "PYTHON=%CONDA_PREFIX%\python.exe"
if not defined PYTHON if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\Scripts\python.exe" set "PYTHON=%VIRTUAL_ENV%\Scripts\python.exe"
if not defined PYTHON set "PYTHON=python"

"%PYTHON%" -m PyInstaller build.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [失败] 打包过程中出错。请确认已激活虚拟环境并安装依赖：pip install -r requirements.txt pyinstaller
    goto :end
)

if exist dist\AnyBar.exe (
    echo.
    echo [成功] 产物: dist\AnyBar.exe
    for %%I in (dist\AnyBar.exe) do echo        大小: %%~zI 字节
) else (
    echo.
    echo [失败] 未找到 dist\AnyBar.exe
)

:end
echo.
pause
endlocal
