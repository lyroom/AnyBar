@echo off
chcp 65001 >nul
setlocal

rem 切到脚本所在目录，保证 data/ 等相对路径正确
cd /d "%~dp0"

rem 优先使用 ANYBAR_PYTHON / 当前激活环境的 pythonw（无控制台黑框），回退至 PATH 中的 pythonw / python
set "PYW="
if defined ANYBAR_PYTHON (
    for %%I in ("%ANYBAR_PYTHON%") do (
        if exist "%%~dpIpythonw.exe" set "PYW=%%~dpIpythonw.exe"
    )
)
if not defined PYW if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\pythonw.exe" set "PYW=%CONDA_PREFIX%\pythonw.exe"
if not defined PYW if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\Scripts\pythonw.exe" set "PYW=%VIRTUAL_ENV%\Scripts\pythonw.exe"
if not defined PYW (
    for /f "delims=" %%I in ('where pythonw 2^>nul') do (
        if not defined PYW set "PYW=%%I"
    )
)

if defined PYW (
    start "" "%PYW%" main.py
    goto :done
)

start "AnyBar" /min python main.py

:done
endlocal
exit
