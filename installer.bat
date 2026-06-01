@echo off
REM Double-click this file to run the One-Click PowerShell installer
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%installer.ps1"
popd
pause
