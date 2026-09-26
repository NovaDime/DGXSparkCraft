@echo off
chcp 65001 >nul
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\scripts\manage.ps1" status --follow %*
set "roundtableExit=%ERRORLEVEL%"
echo.
pause
exit /b %roundtableExit%
