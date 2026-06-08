@echo off
setlocal
set "ROOT=C:\Users\prashantp\Videos\aem-guides-dataset-studio"
set "PY=%ROOT%\venv\Scripts\python.exe"
set "LOG=%ROOT%\tmp\backend-start.log"
if exist "%LOG%" del "%LOG%"
start "" /b cmd /c ""%PY%" "%ROOT%\backend\run_local.py" > "%LOG%" 2>&1"
