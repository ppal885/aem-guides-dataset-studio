@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0RUN_LOCAL_DEV.ps1" %*
