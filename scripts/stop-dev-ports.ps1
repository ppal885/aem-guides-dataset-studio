# Stop listeners on common dev ports (Dataset Studio frontend + API).
$ports = @(5173, 5174, 5175, 8001)
foreach ($port in $ports) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        $procId = $c.OwningProcess
        Write-Host "Stopping PID $procId (port $port)"
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
}
Write-Host "Done."
