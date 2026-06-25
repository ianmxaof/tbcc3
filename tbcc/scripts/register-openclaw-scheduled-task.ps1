# DEPRECATED — use setup-openclaw-tbcc.ps1 + OpenClaw cron instead.
# Unregisters legacy Windows Task Scheduler job TBCC-OpenClaw-Tick.
param(
  [int]$IntervalMinutes = 20,
  [switch]$Unregister,
  [switch]$RunNow
)

$ErrorActionPreference = "Stop"
Write-Host "NOTE: Prefer github.com/openclaw/openclaw cron over this Task Scheduler job." -ForegroundColor DarkYellow
Write-Host "See tbcc/docs/OPENCLAW_TBCC_INTEGRATION.md" -ForegroundColor DarkYellow

$tbccRoot = Split-Path $PSScriptRoot -Parent
$tickPs1 = Join-Path $tbccRoot "scripts\tbcc-flywheel-tick.log.ps1"
$taskName = "TBCC-OpenClaw-Tick"

if (-not (Test-Path -LiteralPath $tickPs1)) {
  $tickPs1 = Join-Path $tbccRoot "scripts\openclaw-tick.log.ps1"
}

if ($Unregister) {
  schtasks /Delete /TN $taskName /F 2>$null | Out-Null
  Write-Host "Removed scheduled task: $taskName" -ForegroundColor Green
  exit 0
}

Write-Host "To unregister: .\register-openclaw-scheduled-task.ps1 -Unregister" -ForegroundColor Cyan
Write-Host "To run flywheel manually: .\run-tbcc-flywheel-tick.ps1" -ForegroundColor Cyan
exit 0
