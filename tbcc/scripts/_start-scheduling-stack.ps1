# One-shot: start Beat + Celery workers when down (used by health remediate).
$ErrorActionPreference = "Continue"
$TbccRoot = Split-Path $PSScriptRoot -Parent
. (Join-Path $PSScriptRoot "tbcc-service-control.ps1")
# Ensure restarts only missing workers — do not also call Start-TbccStackService (was double-spawning).
$report = @(Ensure-TbccSchedulingWorkersSingleton -TbccRoot $TbccRoot -FullStack)
foreach ($row in $report) {
  if ($row.Restarted) {
    Write-Host ("Started {0} (pid {1})" -f $row.Title, $row.KeptPid)
  } elseif ($row.Trimmed -gt 0) {
    Write-Host ("{0}: trimmed {1}; kept pid {2}" -f $row.Title, $row.Trimmed, $row.KeptPid)
  } elseif ($row.KeptPid -gt 0) {
    Write-Host ("{0}: already running (pid {1})" -f $row.Title, $row.KeptPid)
  } else {
    Write-Host ("{0}: not running (start via start.ps1 -WtTabs -Full)" -f $row.Title) -ForegroundColor Yellow
  }
}
