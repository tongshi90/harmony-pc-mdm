# 启动设备模拟器（默认端口 8081，与云侧 8080 互不干扰）
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Port = 8081
if ($env:DEVICE_PORT) { $Port = [int]$env:DEVICE_PORT }

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

function Stop-PortListeners {
    param([int]$Port)
    Write-Host "Cleaning processes on port $Port ..."
    $listenPids = @()
    try {
        $listenPids = @(
            Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty OwningProcess -Unique
        )
    } catch {}
    foreach ($procId in $listenPids) {
        if (-not $procId -or $procId -eq 0) { continue }
        Write-Host "  taskkill /T PID=$procId"
        cmd /c "taskkill /F /T /PID $procId" | Out-Null
    }
    Start-Sleep -Seconds 1
}

if (-not (Test-Path $Python)) {
    Write-Host "Creating venv and installing dependencies ..."
    python -m venv .venv
    & $Python -m pip install -r requirements.txt
}

$DbPath = Join-Path $PSScriptRoot "data\device.db"
if (-not (Test-Path $DbPath)) {
    Write-Host "Initializing device DB (demo seed) ..."
    & $Python (Join-Path $PSScriptRoot "db_device_init.py") --demo
}

Stop-PortListeners -Port $Port

Write-Host ""
Write-Host "Starting device simulator at http://localhost:$Port ..."
Write-Host "Cloud API default: http://127.0.0.1:8080  (override DEVICE_CLOUD_BASE_URL)"
Write-Host "Stop: Ctrl+C"
Write-Host ""

$env:DEVICE_PORT = "$Port"
& $Python -m uvicorn device.main:app --host 0.0.0.0 --port $Port --reload --reload-dir device
