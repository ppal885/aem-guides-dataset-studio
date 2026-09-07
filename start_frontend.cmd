@echo off
setlocal
echo This legacy command now starts the dashboard-only UAC runtime. Use RUN_LOCAL_DEV.cmd for new workflows.
call "%~dp0RUN_LOCAL_DEV.cmd" %*
exit /b %errorlevel%
