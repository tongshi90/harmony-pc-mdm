# Stop Docker preview
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
Write-Host "Stopping Docker container..." -ForegroundColor Cyan
docker compose down
