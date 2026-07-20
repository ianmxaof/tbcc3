# After revenue-island cutover: force home payment/loot Off so Start stack cannot 409.
# Also reminds operator to set TBCC_REVENUE_ISLAND_ACTIVE=1 in tbcc/.env (not auto-written — avoid surprise).
#
#   cd tbcc
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\revenue-island\mark-home-bots-off.ps1

$ErrorActionPreference = "Stop"
$tbccRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$control = Join-Path $tbccRoot "scripts\tbcc-service-control.ps1"
if (-not (Test-Path -LiteralPath $control)) {
  throw "Cannot locate tbcc-service-control.ps1 under $tbccRoot"
}

. $control

Set-TbccServiceUserEnabled -ServiceId "payment" -Enabled $false -TbccRoot $tbccRoot
Set-TbccServiceUserEnabled -ServiceId "loot" -Enabled $false -TbccRoot $tbccRoot

Write-Host ("Home toggles: payment=false loot=false ({0})" -f (Join-Path $tbccRoot ".tbcc-run\service-toggles.json")) -ForegroundColor Green
Write-Host "Also set in tbcc/.env (manual): TBCC_REVENUE_ISLAND_ACTIVE=1" -ForegroundColor Yellow
Write-Host "Then Exit+relaunch tray. Casual Start stack must not spawn home payment/loot." -ForegroundColor Yellow
