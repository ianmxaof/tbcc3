# Optional Windows Task Scheduler — weekly TBCC ship-log tick (Buffer Idea or X queue).
param(
  [ValidateSet("Weekly", "Daily")]
  [string]$Cadence = "Weekly",
  [switch]$Unregister,
  [switch]$RunNow
)

$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $tbccRoot "backend"
$taskName = "TBCC-Ship-Log-Tick"

if ($Unregister) {
  schtasks /Delete /TN $taskName /F 2>$null | Out-Null
  Write-Host "Removed scheduled task (if present): $taskName" -ForegroundColor Green
  exit 0
}

if ($RunNow) {
  Push-Location $backend
  try {
    py -3.13 scripts/run_ship_log_tick.py @args
    exit $LASTEXITCODE
  } finally {
    Pop-Location
  }
}

$action = New-ScheduledTaskAction `
  -Execute "py" `
  -Argument "-3.13 `"$(Join-Path $backend 'scripts\run_ship_log_tick.py')`"" `
  -WorkingDirectory $backend

# Monday 09:00 local
$trigger = if ($Cadence -eq "Daily") {
  New-ScheduledTaskTrigger -Daily -At "09:00"
} else {
  New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "09:00"
}

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Host "Registered: $taskName ($Cadence Monday/daily 09:00)" -ForegroundColor Green
Write-Host "Env: TBCC_SHIP_LOG_AUTO_MODE=idea|queue|share_now (default idea)" -ForegroundColor Cyan
Write-Host "Run now: .\register-ship-log-scheduled-task.ps1 -RunNow" -ForegroundColor Cyan
Write-Host "Dry run: .\register-ship-log-scheduled-task.ps1 -RunNow --dry-run" -ForegroundColor Cyan
