# Running the Backend Server

## Issue
Windows Store Python has permission restrictions that prevent it from running in some contexts.

## Solutions

### Option 1: Run Python Directly (Recommended)
Open a **new PowerShell window** and run:

```powershell
cd c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\backend
C:\Users\prashantp\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe run_local.py
```

### Option 2: Install Python from python.org (Best Long-term Solution)
1. Download Python from: https://www.python.org/downloads/
2. During installation, check **"Add Python to PATH"**
3. After installation, restart your terminal
4. Then run: `python run_local.py` from the backend directory

### Option 3: Use the Fixed Script
Try running the fixed script I created:

```powershell
.\start_backend_direct.ps1
```

### Option 4: Use WSL (Windows Subsystem for Linux)
If you have WSL installed:
```bash
cd /mnt/c/UI_Frameowrk/guides-ui-tests/aem-guides-dataset-studio/backend
python3 run_local.py
```

## Verify Backend is Running
Once started, the backend should be available at:
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## Note
The fixes I made to handle the 500 error are already in place in `backend/app/api/v1/routes/schedule.py`. Once the backend starts, test the `/api/v1/jobs` endpoint again.
