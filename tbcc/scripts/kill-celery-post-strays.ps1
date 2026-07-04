# Trim duplicate Beat / Celery / Celery-Post workers (session lock relief).
# TrimOnly — never spawn new headless workers here (that caused duplicates with start.ps1 WT tabs).
param([switch]$RestartMissing)

. (Join-Path $PSScriptRoot "tbcc-service-control.ps1")
$TbccRoot = Split-Path $PSScriptRoot -Parent
$nsfw = @(Stop-TbccProcessesByCommandMatch -Pattern 'run_nsfw_detect')
if ($RestartMissing) {
  $report = @(Ensure-TbccSchedulingWorkersSingleton -TbccRoot $TbccRoot -FullStack)
} else {
  $report = @(Ensure-TbccSchedulingWorkersSingleton -TbccRoot $TbccRoot -FullStack -TrimOnly)
}
foreach ($row in $report) {
  if ($row.Trimmed -gt 0) {
    Write-Host ("{0}: trimmed {1}; kept pid {2}" -f $row.Title, $row.Trimmed, $row.KeptPid)
  } elseif ($row.Restarted) {
    Write-Host ("{0}: restarted; pid {1}" -f $row.Title, $row.KeptPid)
  } else {
    Write-Host ("{0}: OK (pid {1})" -f $row.Title, $row.KeptPid)
  }
}
Write-Host ("Killed NSFW={0}." -f $nsfw.Count)
