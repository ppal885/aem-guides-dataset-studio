@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0RUN_LOCAL_DEV.ps1" -Stop %*
exit /b %errorlevel%
