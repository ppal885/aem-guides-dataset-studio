# PowerShell script to clear Vite cache
Write-Host "Clearing Vite cache..." -ForegroundColor Yellow

# Remove Vite cache directory
if (Test-Path "node_modules\.vite") {
    Remove-Item -Recurse -Force "node_modules\.vite"
    Write-Host "✓ Vite cache cleared" -ForegroundColor Green
} else {
    Write-Host "✓ No Vite cache found" -ForegroundColor Green
}

# Remove dist directory if exists
if (Test-Path "dist") {
    Remove-Item -Recurse -Force "dist"
    Write-Host "✓ Dist directory cleared" -ForegroundColor Green
}

Write-Host "`nCache cleared! Restart your dev server with: npm run dev" -ForegroundColor Cyan
