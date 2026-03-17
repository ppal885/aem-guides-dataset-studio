# Index DITA 1.2 PDF - calls POST /api/v1/ai/index-dita-pdf
# Run from project root or backend directory. Ensure backend is running on port 8000.

$baseUrl = $env:API_BASE_URL ?? "http://localhost:8000"
$url = "$baseUrl/api/v1/ai/index-dita-pdf"

Write-Host "Indexing DITA 1.2 PDF..." -ForegroundColor Cyan
Write-Host "POST $url" -ForegroundColor Gray
Write-Host ""

try {
    $response = Invoke-RestMethod -Uri $url -Method POST -TimeoutSec 600
    Write-Host "Success!" -ForegroundColor Green
    Write-Host "pages_loaded:  $($response.pages_loaded)"
    Write-Host "chunks_stored: $($response.chunks_stored)"
    if ($response.errors -and $response.errors.Count -gt 0) {
        Write-Host "errors: $($response.errors -join '; ')" -ForegroundColor Yellow
    }
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    Write-Host "Failed (HTTP $statusCode)" -ForegroundColor Red
    Write-Host $_.Exception.Message
    if ($statusCode -eq 404) {
        Write-Host ""
        Write-Host "404 Not Found - try:" -ForegroundColor Yellow
        Write-Host "  1. Restart the backend (stop and run START_BACKEND_SIMPLE.ps1 again)"
        Write-Host "  2. Open http://localhost:8000/docs and search for 'index-dita-pdf'"
        Write-Host "  3. If backend runs on different port, set: `$env:API_BASE_URL='http://localhost:PORT'"
    }
    exit 1
}
