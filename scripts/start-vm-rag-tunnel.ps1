# Forward VM dataset-studio backend (RAG API) to localhost:8001.
# Keep this window open while using aem-guides-evidence MCP in Cursor.
#
# Prerequisite on VM (10.42.46.78):
#   curl -s http://127.0.0.1:8001/health
# Backend must be running (run_local.py or docker compose).

param(
    [string]$VmHost = "10.42.46.78",
    [string]$VmUser = $env:USERNAME,
    [int]$LocalPort = 8001,
    [int]$RemotePort = 8001
)

Write-Host "Opening SSH tunnel: localhost:${LocalPort} -> ${VmHost}:${RemotePort}"
Write-Host "Leave this session running. Test in another terminal:"
Write-Host "  Invoke-WebRequest http://127.0.0.1:${LocalPort}/health -Headers @{ Authorization = 'Bearer dev-bypass' }"
Write-Host ""

ssh -N -L "${LocalPort}:127.0.0.1:${RemotePort}" "${VmUser}@${VmHost}"
