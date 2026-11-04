# 仅打包 Docker 镜像（不启动）
# 用法: .\scripts\build-image.ps1 [-Tag unimdm-demo:latest]
param(
  [string]$Tag = "unimdm-demo:latest"
)

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Building image: $Tag ..." -ForegroundColor Cyan
docker build -t $Tag .
if ($LASTEXITCODE -eq 0) {
  Write-Host "Image ready: $Tag" -ForegroundColor Green
  Write-Host "Run: docker run -d --name unimdm-demo -p <PORT>:80 $Tag" -ForegroundColor DarkGray
} else {
  Write-Host "Image build failed." -ForegroundColor Red
  exit $LASTEXITCODE
}
