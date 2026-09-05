# Stop listeners on the UAC backend and static dashboard development ports.
$ports = @(8001, 8765)
foreach ($port in $ports) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        $procId = $c.OwningProcess
        Write-Host "Stopping PID $procId (port $port)"
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
}
Write-Host "Done."
