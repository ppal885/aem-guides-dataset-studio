@echo off
setlocal
echo This legacy command now delegates to the dashboard-only UAC launcher.
call "%~dp0..\RUN_LOCAL_DEV.cmd" %*
exit /b %errorlevel%
