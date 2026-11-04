# Local preview: http://localhost:8080
# Always serve the web/ directory as document root (avoids 404 when cwd is wrong)
$Root = Split-Path -Parent $PSScriptRoot
Write-Host "UniMDM local server -> http://localhost:8080" -ForegroundColor Cyan
Write-Host "Document root: $Root" -ForegroundColor DarkGray
Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray
python -m http.server 8080 --directory $Root
