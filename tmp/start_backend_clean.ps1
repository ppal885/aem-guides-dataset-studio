$ErrorActionPreference = "Stop"
$out = "C:\Users\prashantp\Videos\aem-guides-dataset-studio\tmp\backend-clean.log"
$err = "C:\Users\prashantp\Videos\aem-guides-dataset-studio\tmp\backend-clean.err"
Remove-Item $out, $err -ErrorAction SilentlyContinue
Start-Process -UseNewEnvironment -FilePath "C:\Users\prashantp\Videos\aem-guides-dataset-studio\venv\Scripts\python.exe" -ArgumentList "run_local.py" -WorkingDirectory "C:\Users\prashantp\Videos\aem-guides-dataset-studio\backend" -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err
