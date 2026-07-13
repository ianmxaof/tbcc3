# Kill hung Cursor-agent PowerShell shells that outlive the chat UI.
# Does NOT touch TBCC tray/supervisor workers or normal interactive terminals.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\cleanup-cursor-agent-shells.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\cleanup-cursor-agent-shells.ps1 -MaxAgeHours 4 -WhatIf
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\cleanup-cursor-agent-shells.ps1 -RegisterScheduledTask
#
# Safe kill fingerprint (ALL must match):
#   - powershell.exe / pwsh.exe
#   - running longer than -MaxAgeHours
#   - command line looks like a Cursor agent one-shot (temp ps-script, agent-tools, or hung remote-worker sync)
#   - NOT a TBCC supervisor / stack / scheduled-task host script

param(
  [double]$MaxAgeHours = 4,
  [switch]$WhatIf,
  [switch]$RegisterScheduledTask,
  [string]$TaskName = "TBCC-Cleanup-Cursor-Agent-Shells"
)

$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$tbccRoot = Split-Path $here -Parent

$protectPatterns = @(
  'tbcc-supervisor\.ps1',
  'tbcc-service-control\.ps1',
  'tbcc-launch-daemon\.ps1',
  'tbcc-stack-cli\.ps1',
  'tbcc-cold-start\.ps1',
  'tbcc-restart-full-stack\.ps1',
  'register-supervisor-autostart\.ps1',
  'register-ship-log-scheduled-task\.ps1',
  'start\.ps1',
  'cleanup-cursor-agent-shells\.ps1'
)

$killPatterns = @(
  '\\AppData\\Local\\Temp\\ps-script-',
  '\\agent-tools\\',
  'sync-scraper-session\.ps1',
  'remote-worker\\.*\.ps1'
)

function Test-ProtectedCmd([string]$cmd) {
  foreach ($pat in $protectPatterns) {
    if ($cmd -match $pat) { return $true }
  }
  return $false
}

function Test-AgentShellCmd([string]$cmd) {
  foreach ($pat in $killPatterns) {
    if ($cmd -match $pat) { return $true }
  }
  # Cursor agent wrappers almost always use both flags together on one-shots
  if ($cmd -match '-NoProfile' -and $cmd -match '-ExecutionPolicy\s+Bypass' -and $cmd -match 'Cursor|cursor') {
    return $true
  }
  return $false
}

if ($RegisterScheduledTask) {
  $scriptPath = Join-Path $here "cleanup-cursor-agent-shells.ps1"
  $arg = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -MaxAgeHours $MaxAgeHours"
  $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arg
  $trigger = New-ScheduledTaskTrigger -Daily -At "08:30AM"
  $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
  Write-Host "Registered scheduled task '$TaskName' (daily 08:30, MaxAgeHours=$MaxAgeHours)" -ForegroundColor Green
  Write-Host "Run now: Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Cyan
  exit 0
}

$cutoff = (Get-Date).AddHours(-1 * [math]::Abs($MaxAgeHours))
$procs = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" -ErrorAction SilentlyContinue)
$killed = 0
$skipped = 0

foreach ($p in $procs) {
  $cmd = [string]($p.CommandLine)
  if (-not $cmd) { continue }

  try {
    $started = [Management.ManagementDateTimeConverter]::ToDateTime($p.CreationDate)
  } catch {
    continue
  }
  if ($started -gt $cutoff) {
    $skipped++
    continue
  }
  if (Test-ProtectedCmd $cmd) {
    $skipped++
    continue
  }
  if (-not (Test-AgentShellCmd $cmd)) {
    $skipped++
    continue
  }

  $ageH = [math]::Round(((Get-Date) - $started).TotalHours, 1)
  $short = if ($cmd.Length -gt 120) { $cmd.Substring(0, 120) + "..." } else { $cmd }
  if ($WhatIf) {
    Write-Host ("[WhatIf] would kill PID {0} age={1}h  {2}" -f $p.ProcessId, $ageH, $short) -ForegroundColor Yellow
    $killed++
    continue
  }
  try {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
    Write-Host ("Killed PID {0} age={1}h  {2}" -f $p.ProcessId, $ageH, $short) -ForegroundColor Yellow
    $killed++
  } catch {
    Write-Host ("Failed PID {0}: {1}" -f $p.ProcessId, $_.Exception.Message) -ForegroundColor Red
  }
}

Write-Host ("Done. killed={0} skipped={1} maxAgeHours={2}" -f $killed, $skipped, $MaxAgeHours) -ForegroundColor Green
Write-Host "UI tip: also trash 'Other Agents' rows in Cursor (stops the agent session; this script clears leftover shells)." -ForegroundColor DarkGray
