# Docker 启动 UniMDM 静态效果图
# 用法: .\scripts\start-docker.ps1 [-Port 8080]
param(
  [int]$Port = 8080
)

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:HOST_PORT = "$Port"
Write-Host "Building and starting Docker container (host port $Port)..." -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -eq 0) {
  Write-Host "UniMDM Docker -> http://localhost:$Port" -ForegroundColor Green
  Write-Host "Stop: .\scripts\stop-docker.ps1" -ForegroundColor DarkGray
} else {
  Write-Host "Docker start failed. Is Docker installed and running?" -ForegroundColor Red
  exit $LASTEXITCODE
}
