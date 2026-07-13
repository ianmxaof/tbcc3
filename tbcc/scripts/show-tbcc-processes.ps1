# TBCC process monitor — map generic python.exe rows to named services (CPU/RAM/ports).

# Usage:

#   cd tbcc\scripts

#   .\show-tbcc-processes.ps1 -Full

#   .\show-tbcc-processes.ps1 -Full -LogIssues

#   .\show-tbcc-processes.ps1 -Watch -IntervalSec 5

param(

  [string]$TbccRoot = "",

  [switch]$Full,

  [switch]$Watch,

  [switch]$LogIssues,

  [switch]$Quiet,

  [int]$IntervalSec = 5

)



$ErrorActionPreference = "Continue"

if (-not $TbccRoot) {

  $TbccRoot = Split-Path $PSScriptRoot -Parent

}

. (Join-Path $PSScriptRoot "tbcc-service-control.ps1")

. (Join-Path $PSScriptRoot "tbcc-error-hub.ps1")

. (Join-Path $PSScriptRoot "tbcc-process-audit.ps1")



function Show-TbccProcessFootprint {
  # One-line footprint: workers vs shells vs WT host vs supervisor, plus a waste count
  # (duplicate workers + orphans + extra WT hosts/supervisors). Steady-state lean target
  # is ~10 workers, 1 WT host, ~10-12 cmd tab shells, ~1 supervisor, waste 0.
  param([Parameter(Mandatory = $true)]$Report, [Parameter(Mandatory = $true)][string]$Root)

  $workerCount = [int]((@($Report.Services | Where-Object { $_.Status -eq 'up' }) | Measure-Object -Property PidCount -Sum).Sum)
  $rootEsc = [regex]::Escape($Root)
  $shellProcs = @(Get-CimInstance Win32_Process -Filter "Name='cmd.exe' OR Name='powershell.exe' OR Name='pwsh.exe' OR Name='WindowsTerminal.exe'" -ErrorAction SilentlyContinue)

  $wtCount = @($shellProcs | Where-Object { [string]$_.Name -ieq 'WindowsTerminal.exe' }).Count
  $supCount = @($shellProcs | Where-Object { $_.CommandLine -match 'tbcc-supervisor\.ps1' }).Count
  $cmdShells = @($shellProcs | Where-Object {
      [string]$_.Name -ieq 'cmd.exe' -and $_.CommandLine -and ($_.CommandLine -match $rootEsc -or $_.CommandLine -match 'run-tbcc-service|Launch-TBCC|tbcc-orchestrate|tbcc-cold-start')
    }).Count
  $psWrappers = @($shellProcs | Where-Object {
      ([string]$_.Name -ieq 'powershell.exe' -or [string]$_.Name -ieq 'pwsh.exe') -and $_.CommandLine -and
      ($_.CommandLine -match 'run-tbcc-service|run-tbcc-stackwatch|run-tbcc-service\.ps1') -and ($_.CommandLine -notmatch 'tbcc-supervisor\.ps1')
    }).Count

  $waste = [int]$Report.DupCount + [int]$Report.OrphanCount + [Math]::Max(0, $wtCount - 1) + [Math]::Max(0, $supCount - 1)

  if (-not $Quiet) {
    Write-Host ""
    Write-Host "  Footprint (lean target: ~10 workers / 1 WT / ~10-12 cmd / 1 supervisor / waste 0)" -ForegroundColor Yellow
    $wasteColor = if ($waste -gt 0) { "Red" } else { "Green" }
    Write-Host ("  {0} workers | {1} WT host | {2} cmd shells | {3} PS wrappers | {4} supervisor(s) | waste: {5}" -f `
        $workerCount, $wtCount, $cmdShells, $psWrappers, $supCount, $waste) -ForegroundColor $wasteColor
  }
  return [pscustomobject]@{ Workers = $workerCount; WtHosts = $wtCount; CmdShells = $cmdShells; PsWrappers = $psWrappers; Supervisors = $supCount; Waste = $waste }
}

function Show-TbccProcessReport {

  param([string]$Root, [bool]$FullStack)



  $report = Get-TbccProcessAuditReport -Root $Root -FullStack:$FullStack

  $issues = @($report.Issues)

  $all = Get-TbccProcessAuditAllProcesses

  $lean = $report.Lean



  if (-not $Quiet) {

    Clear-Host

    Write-Host ""

    Write-Host "  TBCC process monitor" -ForegroundColor Cyan

    Write-Host ("  Root: " + $Root) -ForegroundColor DarkGray

    Write-Host ("  {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) -ForegroundColor DarkGray

    if ($lean) {

      Write-Host "  Profile: lean (Album Composer on; forum/macro/admin/enrichment off unless tray-enabled)" -ForegroundColor DarkCyan

    }

    Write-Host ""



    Write-Host "  Services (name -> python/node/bun PIDs, RAM)" -ForegroundColor Yellow

    foreach ($row in $report.Services) {

      $color = if ($row.Status -eq "up") { "Green" } else { "DarkGray" }

      if ($row.PidCount -gt 1) { $color = "Red" }

      $port = if ($row.Port -gt 0) { (":" + $row.Port) } else { "" }

      $pidLabel = if ($row.Pids) { $row.Pids } else { "-" }

      $dupTag = if ($row.PidCount -gt 1) { " DUP" } else { "" }

      Write-Host ("  {0,-22} [{1,4}]{2}{3}  RAM {4,6} MB  PID {5}" -f $row.Title, $row.Status, $port, $dupTag, $row.RamMb, $pidLabel) -ForegroundColor $color

      $procs = @()
      if ($row.CommandMatch) {
        $procs = @(Get-TbccProcessAuditMatches -Pattern $row.CommandMatch -All $all)
      }

      foreach ($pr in $procs | Select-Object -First 2) {

        $cmd = [string]$pr.CommandLine

        if ($cmd.Length -gt 110) { $cmd = $cmd.Substring(0, 107) + "..." }

        Write-Host ("      " + $cmd) -ForegroundColor DarkGray

      }

    }



    $null = Show-TbccProcessFootprint -Report $report -Root $Root

    Write-Host ""

    Write-Host "  Listening ports" -ForegroundColor Yellow

    foreach ($row in $report.Ports) {

      $c = if ($row.Listening) { "Green" } else { "DarkGray" }

      $listenLabel = if ($row.Listening) { "listen" } else { "-" }

      Write-Host ("  :{0,-5} {1,-6}  PID {2}" -f $row.Port, $listenLabel, $row.Pids) -ForegroundColor $c

    }



    if ($lean -and $report.LeanCount -gt 0) {

      Write-Host ""

      Write-Host "  Lean profile violations (should not be running)" -ForegroundColor Yellow

      foreach ($msg in $issues | Where-Object { $_ -match "lean profile" }) {

        Write-Host ("  ! {0}" -f $msg) -ForegroundColor Red

      }

    } elseif ($lean) {

      Write-Host ""

      Write-Host "  Lean profile violations (should not be running)" -ForegroundColor Yellow

      Write-Host "  (none)" -ForegroundColor DarkGray

    }



    $orphanIssues = @($issues | Where-Object { $_ -match "^Orphan PID" })

    if ($orphanIssues.Count -gt 0) {

      Write-Host ""

      Write-Host "  Unlabeled TBCC python (not matched above)" -ForegroundColor Yellow

      foreach ($msg in $orphanIssues) {

        Write-Host ("  {0}" -f $msg) -ForegroundColor DarkYellow

      }

    }



    Write-Host ""

    Write-Host "  Docker (Postgres/Redis only - most TBCC apps run on host)" -ForegroundColor Yellow

    try {

      $dockerPs = docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>$null

      if ($LASTEXITCODE -eq 0 -and $dockerPs) {

        $dockerPs | ForEach-Object { Write-Host ("  " + $_) -ForegroundColor Gray }

      } else {

        Write-Host "  (docker not running or no containers)" -ForegroundColor DarkGray

      }

    } catch {

      Write-Host "  (docker CLI unavailable)" -ForegroundColor DarkGray

    }



    $apiUrl = "http://127.0.0.1:8000/health/system"

    Write-Host ""

    Write-Host "  API health (bottlenecks: session lock, import queue, Redis)" -ForegroundColor Yellow

    try {

      $resp = Invoke-RestMethod -Uri $apiUrl -TimeoutSec 4 -ErrorAction Stop

      $ok = [bool]$resp.ok

      Write-Host ("  ok={0}" -f $ok) -ForegroundColor $(if ($ok) { "Green" } else { "Red" })

      if ($resp.issues) {

        foreach ($issue in @($resp.issues)) {

          $msg = if ($issue.message) { $issue.message } else { ($issue | ConvertTo-Json -Compress) }

          Write-Host ("    - {0}" -f $msg) -ForegroundColor DarkYellow

        }

      }

      if ($resp.import_jobs_active -ne $null) {

        Write-Host ("  active import jobs: {0}" -f $resp.import_jobs_active) -ForegroundColor Gray

      }

    } catch {

      Write-Host "  API not reachable at $apiUrl (start TBCC-Backend)" -ForegroundColor DarkGray

    }



    Write-Host ""

    Write-Host "  Tips" -ForegroundColor DarkCyan

    Write-Host "  - StackWatch tab audits every 60s (.tbcc-run\process-audit.json)." -ForegroundColor DarkGray

    Write-Host "  - Tray panel Stack module shows live audit micro-summary." -ForegroundColor DarkGray

    Write-Host "  - Audit: .\show-tbcc-processes.ps1 -Full -LogIssues" -ForegroundColor DarkGray

    Write-Host ""



    if ($issues.Count -gt 0) {

      Write-Host ("  {0} issue(s) detected - tray Stop then Cold start recommended." -f $issues.Count) -ForegroundColor Red

    }

  }



  return $issues

}



if ($Watch) {

  if ($IntervalSec -lt 2) { $IntervalSec = 2 }

  while ($true) {

    $found = Show-TbccProcessReport -Root $TbccRoot -FullStack:$Full

    if ($LogIssues -and $found.Count -gt 0) {

      foreach ($msg in $found) {

        Write-TbccErrorHubEntry -TbccRoot $TbccRoot -ServiceName "TBCC-ProcessAudit" -Level "WARN" -Message $msg

      }

    }

    $report = Get-TbccProcessAuditReport -Root $TbccRoot -FullStack:$Full

    $null = Write-TbccProcessAuditSnapshot -TbccRoot $TbccRoot -Report $report

    Start-Sleep -Seconds $IntervalSec

  }

}



if (-not $PSBoundParameters.ContainsKey("Full")) {

  $probe = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {

    $_.CommandLine -match "celery_app|uvicorn app\.main"

  }

  if ($probe) { $Full = $true }

}



$reportIssues = Show-TbccProcessReport -Root $TbccRoot -FullStack:$Full

$report = Get-TbccProcessAuditReport -Root $TbccRoot -FullStack:$Full

$null = Write-TbccProcessAuditSnapshot -TbccRoot $TbccRoot -Report $report



if ($LogIssues -and $reportIssues.Count -gt 0) {

  foreach ($msg in $reportIssues) {

    Write-TbccErrorHubEntry -TbccRoot $TbccRoot -ServiceName "TBCC-ProcessAudit" -Level "WARN" -Message $msg

  }

  if (-not $Quiet) {

    Write-Host "  Logged to .tbcc-run\error-hub.log" -ForegroundColor DarkCyan

  }

}

