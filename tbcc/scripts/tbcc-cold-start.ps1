# Cold start launcher — run from tray supervisor (one window; tray stays alive).
# Uses Windows PowerShell 5.1 (powershell.exe), not pwsh — see docs/TBCC_PIPELINE.md.
#
#   powershell -File tbcc\scripts\tbcc-cold-start.ps1
#   powershell -File tbcc\scripts\tbcc-cold-start.ps1 -NoOpen

param([switch]$NoOpen)

$ErrorActionPreference = "Continue"
trap {
  Write-Host ""
  Write-Host ("FATAL: " + $_.Exception.Message) -ForegroundColor Red
  if ($_.ScriptStackTrace) { Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray }
  Read-Host "Press Enter to close"
  exit 1
}

$tbccDir = Split-Path -Parent $PSScriptRoot
$controlScript = Join-Path $PSScriptRoot "tbcc-service-control.ps1"
$startPs1 = Join-Path $tbccDir "start.ps1"
$launcherPid = $PID

Write-Host ("TBCC cold-start launcher PID={0} PowerShell {1}" -f $launcherPid, $PSVersionTable.PSVersion) -ForegroundColor DarkGray

if (-not (Test-Path -LiteralPath $controlScript)) {
  Write-Host "Missing $controlScript" -ForegroundColor Red
  Read-Host "Press Enter to close"
  exit 1
}
if (-not (Test-Path -LiteralPath $startPs1)) {
  Write-Host "Missing $startPs1" -ForegroundColor Red
  Read-Host "Press Enter to close"
  exit 1
}

. $controlScript

Write-Host "TBCC cold start" -ForegroundColor Cyan
Write-Host "  [1/2] Stopping prior TBCC stack (this window PID $launcherPid is protected)..." -ForegroundColor Yellow
$gone = Stop-TbccPriorStackWindows -TbccRoot $tbccDir -FullStack -Wait -MaxWaitSeconds 60 -ExcludeProcessIds @($launcherPid)
if ($gone) {
  Write-Host "  Prior stack fully stopped." -ForegroundColor Green
} else {
  Write-Host "  WARNING: Prior stack may still be running. Check TBCC-Errors tab or :8000 / :5173." -ForegroundColor Red
}

Write-Host "  [2/2] Running start.ps1 in this window (services open in Windows Terminal)..." -ForegroundColor Yellow
Write-Host ""

$startArgs = @("-Full", "-WtTabs", "-SkipPriorStackStop")
if ($NoOpen) { $startArgs += "-NoOpen" }

try {
  & $startPs1 @startArgs
} catch {
  Write-Host ""
  Write-Host ("start.ps1 failed: " + $_.Exception.Message) -ForegroundColor Red
  if ($_.ScriptStackTrace) { Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray }
}

Write-Host ""
Write-Host "Cold-start launcher finished (PID $launcherPid)." -ForegroundColor Green
Write-Host "Service tabs: Windows Terminal (TBCC-Errors first). This window stays open." -ForegroundColor Gray
Write-Host ""
