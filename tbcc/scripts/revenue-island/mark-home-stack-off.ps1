# VM-only cutover: disable home tray services that duplicate revenue island.
# Run after island is healthy. Home keeps dashboard (UI only) — point at api.powercore.app.
#
#   cd tbcc
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\revenue-island\mark-home-stack-off.ps1

$ErrorActionPreference = "Stop"
$tbccRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$control = Join-Path $tbccRoot "scripts\tbcc-service-control.ps1"
$cli = Join-Path $tbccRoot "scripts\tbcc-stack-cli.ps1"
if (-not (Test-Path -LiteralPath $control)) {
  throw "Cannot locate tbcc-service-control.ps1 under $tbccRoot"
}

. $control

$islandIds = @(
  "backend",
  "beat",
  "celery",
  "celery_post",
  "celery_post_scheduler",
  "celery_ops",
  "payment",
  "loot"
)

foreach ($id in $islandIds) {
  Write-Host ("Stopping {0}..." -f $id) -ForegroundColor DarkGray
  & powershell -NoProfile -ExecutionPolicy Bypass -File $cli -Action Stop -Service $id 2>&1 | Out-Null
  Set-TbccServiceUserEnabled -ServiceId $id -Enabled $false -TbccRoot $tbccRoot
}

Write-Host ""
Write-Host "Home island-duplicating services: STOPPED + tray toggles OFF" -ForegroundColor Green
Write-Host "  $($islandIds -join ', ')" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Island truth: https://api.powercore.app/health" -ForegroundColor Cyan
Write-Host "Dashboard (home UI only):  cd tbcc/dashboard && npm run dev:island" -ForegroundColor Cyan
Write-Host "Confirm tbcc/.env has TBCC_REVENUE_ISLAND_ACTIVE=1 — then Exit+relaunch tray." -ForegroundColor Yellow
