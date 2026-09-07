@echo off
setlocal
call "%~dp0RUN_LOCAL_DEV.cmd" -Open %*
exit /b %errorlevel%
