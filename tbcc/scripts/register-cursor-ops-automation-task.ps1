# Register Windows Task Scheduler: TBCC Cursor ops automation tick every N minutes.
param(
  [int]$IntervalMinutes = 15,
  [switch]$Unregister,
  [switch]$RunNow
)

$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path $PSScriptRoot -Parent
$tickPs1 = Join-Path $tbccRoot "scripts\cursor-ops-automation-tick.log.ps1"
$taskName = "TBCC-Cursor-Ops-Triage"

if (-not (Test-Path -LiteralPath $tickPs1)) {
  Write-Host "Missing: $tickPs1" -ForegroundColor Red
  exit 1
}

if ($Unregister) {
  schtasks /Delete /TN $taskName /F 2>$null | Out-Null
  Write-Host "Removed scheduled task: $taskName" -ForegroundColor Green
  exit 0
}

$IntervalMinutes = [Math]::Max(5, [Math]::Min(120, $IntervalMinutes))
$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$tickPs1`"" `
  -WorkingDirectory $tbccRoot

$start = (Get-Date).Date.AddMinutes(2)
if ($start -lt (Get-Date)) { $start = (Get-Date).AddMinutes(2) }
$trigger = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

try { schtasks /Delete /TN $taskName /F 2>$null | Out-Null } catch {}
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "TBCC Cursor ops triage tick (poll alerts + flywheel; requires Backend :8000)" | Out-Null

Write-Host "Registered: $taskName (every ${IntervalMinutes}m)" -ForegroundColor Green
Write-Host "  Script: $tickPs1" -ForegroundColor Gray

if ($RunNow) {
  Write-Host "Running tick now..." -ForegroundColor Cyan
  & $tickPs1
}
