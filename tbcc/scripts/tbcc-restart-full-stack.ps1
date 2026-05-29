# Full stack restart launcher — run from tray supervisor (keeps tray process out of stop/kill logic).
#   powershell -File tbcc\scripts\tbcc-restart-full-stack.ps1

$ErrorActionPreference = "Continue"
$tbccDir = Split-Path -Parent $PSScriptRoot
$controlScript = Join-Path $PSScriptRoot "tbcc-service-control.ps1"
$startPs1 = Join-Path $tbccDir "start.ps1"

if (-not (Test-Path -LiteralPath $controlScript)) {
  Write-Host "Missing $controlScript" -ForegroundColor Red
  exit 1
}
if (-not (Test-Path -LiteralPath $startPs1)) {
  Write-Host "Missing $startPs1" -ForegroundColor Red
  exit 1
}

. $controlScript

Write-Host "TBCC full stack restart" -ForegroundColor Cyan
Write-Host "  [1/2] Stopping prior services and Windows Terminal tab hosts..." -ForegroundColor Yellow
$gone = Stop-TbccPriorStackWindows -TbccRoot $tbccDir -FullStack -Wait -MaxWaitSeconds 60
if ($gone) {
  Write-Host "  Prior stack fully stopped (ports free, no TBCC terminal hosts)." -ForegroundColor Green
} else {
  Write-Host "  WARNING: Prior stack may still be running (check for extra Windows Terminal windows or :8000 / :5173 in use)." -ForegroundColor Red
}

Write-Host "  [2/2] Starting start.ps1 -Full -WtTabs -NoOpen (launcher stays open)..." -ForegroundColor Yellow
Write-Host ""

& $startPs1 -Full -WtTabs -NoOpen
