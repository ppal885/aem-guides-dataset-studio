@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0register_claude.ps1" %*
