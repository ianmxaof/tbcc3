# Start everything needed for Last.fm listening relay (home tray stack).
# Usage (from tbcc/):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-listening-relay-stack.ps1
#
# Does NOT fix a dead Telethon session — if posts stay "failed", run:
#   cd backend
#   py -3.13 scripts\login_telethon_sessions.py
# then restart this script.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Cli = Join-Path $Root "scripts\tbcc-stack-cli.ps1"

$relayServices = @(
  "backend",
  "beat",
  "celery_ops",
  "celery_post"
)

Write-Host "`nTBCC listening relay — starting required services..." -ForegroundColor Cyan
foreach ($id in $relayServices) {
  Write-Host "  -> $id" -ForegroundColor DarkGray
  & powershell -NoProfile -ExecutionPolicy Bypass -File $Cli -Action Start -Service $id | Out-Null
  Start-Sleep -Seconds 2
}

Write-Host "`nStatus:" -ForegroundColor Cyan
& powershell -NoProfile -ExecutionPolicy Bypass -File $Cli -Action Status | ConvertFrom-Json |
  Select-Object -ExpandProperty services |
  Where-Object { $relayServices -contains $_.id } |
  ForEach-Object {
    $color = if ($_.status -eq "up") { "Green" } else { "Red" }
    Write-Host ("  [{0}] {1}" -f $_.status, $_.title) -ForegroundColor $color
  }

Write-Host "`nSmoke checks:" -ForegroundColor Cyan
Write-Host '  curl -s -X POST http://127.0.0.1:8000/listening-relay-settings/test-post'
Write-Host '  curl -s "http://127.0.0.1:8000/listening-relay-settings/history?limit=3"'
Write-Host "`nIf history shows 'two different IP addresses' — re-login (interactive):" -ForegroundColor Yellow
Write-Host "  cd $Root\backend"
Write-Host "  py -3.13 scripts\login_telethon_sessions.py"
Write-Host "  (Stop revenue-island worker_post first if island still uses the same session.)`n"
