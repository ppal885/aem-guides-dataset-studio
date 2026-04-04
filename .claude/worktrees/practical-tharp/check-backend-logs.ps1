# PowerShell script to check backend logs for database/table initialization

Write-Host "Checking backend logs for database initialization..." -ForegroundColor Green
Write-Host ""

docker-compose logs backend | Select-String -Pattern "database|table|initialized|migration|create_all" -CaseSensitive:$false

Write-Host ""
Write-Host "To see all backend logs, run:" -ForegroundColor Yellow
Write-Host "  docker-compose logs backend" -ForegroundColor Cyan
Write-Host ""
Write-Host "To follow logs in real-time:" -ForegroundColor Yellow
Write-Host "  docker-compose logs -f backend" -ForegroundColor Cyan
