# Optional Windows Task Scheduler job for TBCC internal flywheel tick.
# Prefer github.com/openclaw/openclaw cron + TBCC MCP for autonomous ops when gateway is up.
param(
  [int]$IntervalMinutes = 20,
  [switch]$Unregister,
  [switch]$RunNow
)

$ErrorActionPreference = "Stop"
Write-Host "NOTE: Internal TBCC flywheel tick — not the OpenClaw gateway." -ForegroundColor DarkGray
Write-Host "Prefer OpenClaw cron + MCP when gateway is running. See tbcc/docs/OPENCLAW_TBCC_INTEGRATION.md" -ForegroundColor DarkYellow

$tbccRoot = Split-Path $PSScriptRoot -Parent
$tickPs1 = Join-Path $tbccRoot "scripts\tbcc-flywheel-tick.log.ps1"
$taskName = "TBCC-Flywheel-Tick"
$legacyTaskName = "TBCC-OpenClaw-Tick"

if ($Unregister) {
  $ErrorActionPreference = "Continue"
  foreach ($tn in @($taskName, $legacyTaskName)) {
    schtasks /Delete /TN $tn /F 2>$null | Out-Null
    Write-Host "Removed scheduled task (if present): $tn" -ForegroundColor Green
  }
  exit 0
}

if ($RunNow) {
  & $tickPs1 -TbccRoot $tbccRoot
  exit $LASTEXITCODE
}

Write-Host "To unregister: .\register-flywheel-scheduled-task.ps1 -Unregister" -ForegroundColor Cyan
Write-Host "To run flywheel manually: .\run-tbcc-flywheel-tick.ps1" -ForegroundColor Cyan
exit 0
