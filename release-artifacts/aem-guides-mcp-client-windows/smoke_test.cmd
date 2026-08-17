@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0smoke_test.ps1" %*
