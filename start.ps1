# 启动云侧服务（前端 + API）
# - 启动前会清理占用 8080 的旧进程，避免跑到旧代码
# - 使用 uvicorn --reload：修改 app/ 下 Python 会自动重载
# - 修改 web/ 静态前端：浏览器 Ctrl+F5 刷新即可（无需重启）
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Port = 8080
$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

function Stop-PortListeners {
    param([int]$Port)
    Write-Host "Cleaning processes on port $Port ..."

    # 1) 按监听端口结束进程树
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

    # 2) 再扫一遍本项目相关的 python（防止僵尸 reloader / spawn 子进程）
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -match [regex]::Escape($PSScriptRoot) -or
                $_.CommandLine -match 'uvicorn app\.main' -or
                ($_.CommandLine -match 'run\.py' -and $_.CommandLine -match 'python')
            )
        } |
        ForEach-Object {
            Write-Host "  taskkill project PID=$($_.ProcessId)"
            cmd /c "taskkill /F /T /PID $($_.ProcessId)" | Out-Null
        }

    Start-Sleep -Seconds 1

    $left = @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    )
    if ($left.Count -gt 0) {
        Write-Host "WARNING: port $Port still has LISTEN entries. If bind fails, close other terminals running the server and retry." -ForegroundColor Yellow
    } else {
        Write-Host "Port $Port is free."
    }
}

if (-not (Test-Path $Python)) {
    Write-Host "Creating venv and installing dependencies ..."
    python -m venv .venv
    & $Python -m pip install -r requirements.txt
}

Stop-PortListeners -Port $Port

Write-Host ""
Write-Host "Starting MDM at http://localhost:$Port ..."
Write-Host "Default account: admin / Ab12345678 (first seed only)"
Write-Host "Hot reload: ON (Python changes under app/ auto-restart)"
Write-Host "Frontend: edit web/ then refresh browser (Ctrl+F5)"
Write-Host "Stop: Ctrl+C in this terminal"
Write-Host ""

# reload=True 在 run.py 中；此处直接调 uvicorn 便于看到完整参数
& $Python -m uvicorn app.main:app --host 0.0.0.0 --port $Port --reload --reload-dir app
