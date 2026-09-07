@echo off
setlocal
echo start_both.cmd is retained for compatibility; use RUN_LOCAL_DEV.cmd for new workflows.
call "%~dp0RUN_LOCAL_DEV.cmd" %*
exit /b %errorlevel%
