@echo off
setlocal
title LUT Studio Generator
color 0B
cls

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo.
echo  ========================================================
echo                   LUT STUDIO GENERATOR
echo  ========================================================
echo.
echo    [+] Professional Color Grading Suite
echo    [+] Smart Presets and Manual Adjustment
echo    [+] Real-time Video Preview
echo    [+] FFmpeg Rendering with optional NVENC
echo.

echo  [Checking Runtime]

set "PYTHON_EXE="
for /d %%D in ("%SCRIPT_DIR%bin\python-*-embed-amd64") do (
    if exist "%%~fD\python.exe" set "PYTHON_EXE=%%~fD\python.exe"
)

if not defined PYTHON_EXE (
    color 0C
    echo    [!] Portable Python was not found.
    echo.
    echo  Run install.bat first, then run Start.bat again.
    echo.
    pause
    exit /b 1
)
echo    [+] Python:       Found - Portable

if exist "%SCRIPT_DIR%bin\ffmpeg\ffmpeg.exe" (
    echo    [+] FFmpeg:       Found - Portable
    set "PATH=%SCRIPT_DIR%bin\ffmpeg;%PATH%"
) else (
    color 0C
    echo    [!] FFmpeg:       Not found.
    echo.
    echo  Run install.bat first, then run Start.bat again.
    echo.
    pause
    exit /b 1
)

set "PYTHONPATH=%SCRIPT_DIR%src;%SCRIPT_DIR%;%PYTHONPATH%"
set PYTHONDONTWRITEBYTECODE=1
echo.

if not exist "src\app.py" (
    color 0C
    echo  [!] Missing core component: src\app.py
    pause
    exit /b 1
)
if not exist "src\randomizer_stochastic_parametric.py" (
    color 0C
    echo  [!] Missing core component: src\randomizer_stochastic_parametric.py
    pause
    exit /b 1
)
if not exist "src\randomizer_arri_logc4.py" (
    color 0C
    echo  [!] Missing core component: src\randomizer_arri_logc4.py
    pause
    exit /b 1
)
if not exist "src\image_mode.py" (
    color 0C
    echo  [!] Missing core component: src\image_mode.py
    pause
    exit /b 1
)

echo    Using runtime: %PYTHON_EXE%
echo.
echo  [INFO] Launching Interface...
echo.

"%PYTHON_EXE%" src\app.py

if errorlevel 1 pause
