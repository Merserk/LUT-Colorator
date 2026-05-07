@echo off
setlocal
title LUT Studio Generator Installer

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo.
echo  ========================================================
echo            LUT STUDIO GENERATOR - INSTALLER
echo  ========================================================
echo.
echo  This will install the portable runtime into:
echo  %SCRIPT_DIR%bin
echo.

where powershell >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Windows PowerShell was not found.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\install.ps1"
if errorlevel 1 (
    echo.
    echo  [ERROR] Install failed. Check the messages above.
    pause
    exit /b 1
)

echo.
echo  [OK] Install complete.
echo  Run start.bat to launch the app.
echo.
pause
