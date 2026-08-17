@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0doctor_claude.ps1" %*
