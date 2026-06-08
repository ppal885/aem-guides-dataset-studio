@echo off
setlocal
set "ROOT=C:\Users\prashantp\Videos\aem-guides-dataset-studio"
set "PY=%ROOT%\venv\Scripts\python.exe"
set "LOG=%ROOT%\tmp\frontend-start.log"
if exist "%LOG%" del "%LOG%"
start "" /b cmd /c ""%PY%" "%ROOT%\tmp\frontend_proxy.py" > "%LOG%" 2>&1"
