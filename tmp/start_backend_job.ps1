$ErrorActionPreference = "Stop"
Start-Job -Name "CodexBackendJob" -ScriptBlock {
    Set-Location "C:\Users\prashantp\Videos\aem-guides-dataset-studio\backend"
    & "C:\Users\prashantp\Videos\aem-guides-dataset-studio\venv\Scripts\python.exe" "run_local.py"
} | Out-Null
