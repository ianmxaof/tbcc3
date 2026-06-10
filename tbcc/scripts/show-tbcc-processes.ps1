# TBCC process monitor — map generic python.exe rows to named services (CPU/RAM/ports).
# Usage:
#   cd tbcc\scripts
#   .\show-tbcc-processes.ps1
#   .\show-tbcc-processes.ps1 -Full
#   .\show-tbcc-processes.ps1 -Watch -IntervalSec 5
param(
  [string]$TbccRoot = "",
  [switch]$Full,
  [switch]$Watch,
  [int]$IntervalSec = 5
)

$ErrorActionPreference = "Continue"
if (-not $TbccRoot) {
  $TbccRoot = Split-Path $PSScriptRoot -Parent
}
. (Join-Path $PSScriptRoot "tbcc-service-control.ps1")

$extraServices = @(
  [pscustomobject]@{ Id = "watch"; Title = "TBCC-WatchOrganizer"; Port = 0; CommandMatch = "watch_folder_organizer" }
)

function Get-TbccAllProcesses {
  @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^(python|py|node|bun|redis|postgres|com\.docker|wsl|WindowsTerminal|wt)\.exe$' -or $_.Name -eq 'vmmemWSL' })
}

function Get-TbccProcessMatches {
  param([string]$Pattern, $All = $null)
  if (-not $All) { $All = Get-TbccAllProcesses }
  @($All | Where-Object { $_.CommandLine -and ($_.CommandLine -match $Pattern) })
}

function Format-TbccRamMb {
  param([long]$Bytes)
  if ($Bytes -le 0) { return "-" }
  return ("{0:N0}" -f [math]::Round($Bytes / 1MB, 0))
}

function Get-TbccProcessRamBytes {
  param([int[]]$Pids)
  $sum = 0L
  foreach ($procId in ($Pids | Select-Object -Unique)) {
    try {
      $p = Get-Process -Id $procId -ErrorAction Stop
      $sum += [long]$p.WorkingSet64
    } catch {}
  }
  return $sum
}

function Get-TbccPortOwners {
  $rows = @()
  $ports = @(8000, 8001, 8002, 5173, 3000, 3001, 6379, 5432)
  foreach ($port in $ports) {
    $listen = $false
    $pids = @()
    try {
      if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        $conns = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
        if ($conns.Count -gt 0) {
          $listen = $true
          $pids = @($conns | Select-Object -ExpandProperty OwningProcess -Unique)
        }
      }
    } catch {}
    if (-not $listen) {
      $listen = Test-TbccPortListening -Port $port
    }
    $rows += [pscustomobject]@{ Port = $port; Listening = $listen; Pids = ($pids -join ", ") }
  }
  return $rows
}

function Show-TbccProcessReport {
  param([string]$Root, [bool]$FullStack)

  $all = Get-TbccAllProcesses
  $services = @(Get-TbccStackServices -TbccRoot $Root -FullStack:$FullStack) + $extraServices
  $matchedPids = New-Object System.Collections.Generic.HashSet[int]

  Clear-Host
  Write-Host ""
  Write-Host "  TBCC process monitor" -ForegroundColor Cyan
  Write-Host ("  Root: " + $Root) -ForegroundColor DarkGray
  Write-Host ("  {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) -ForegroundColor DarkGray
  Write-Host ""

  Write-Host "  Services (name -> python/node/bun PIDs, RAM)" -ForegroundColor Yellow
  foreach ($svc in $services) {
    $procs = @(Get-TbccProcessMatches -Pattern $svc.CommandMatch -All $all)
    foreach ($pr in $procs) { [void]$matchedPids.Add([int]$pr.ProcessId) }
    $pids = @($procs | Select-Object -ExpandProperty ProcessId -Unique)
    $ram = Get-TbccProcessRamBytes -Pids $pids
    $status = if (Test-TbccServiceProcessRunning -Service $svc) { "up" } else { "down" }
    $color = if ($status -eq "up") { "Green" } else { "DarkGray" }
    $port = if ($svc.Port -gt 0) { (":" + $svc.Port) } else { "" }
    $pidLabel = if ($pids.Count) { $pids -join ", " } else { "-" }
    Write-Host ("  {0,-22} [{1,4}]{2}  RAM {3,6} MB  PID {4}" -f $svc.Title, $status, $port, (Format-TbccRamMb $ram), $pidLabel) -ForegroundColor $color
    foreach ($pr in $procs | Select-Object -First 2) {
      $cmd = [string]$pr.CommandLine
      if ($cmd.Length -gt 110) { $cmd = $cmd.Substring(0, 107) + "..." }
      Write-Host ("      " + $cmd) -ForegroundColor DarkGray
    }
  }

  Write-Host ""
  Write-Host "  Listening ports" -ForegroundColor Yellow
  foreach ($row in (Get-TbccPortOwners)) {
    $c = if ($row.Listening) { "Green" } else { "DarkGray" }
    $listenLabel = if ($row.Listening) { "listen" } else { "-" }
    Write-Host ("  :{0,-5} {1,-6}  PID {2}" -f $row.Port, $listenLabel, $row.Pids) -ForegroundColor $c
  }

  $tbccRootEsc = [regex]::Escape($Root)
  $orphan = @($all | Where-Object {
      $_.Name -match '^python\.exe$' -and $_.CommandLine -and ($_.CommandLine -match $tbccRootEsc) -and -not ($matchedPids.Contains([int]$_.ProcessId))
    })
  if ($orphan.Count -gt 0) {
    Write-Host ""
    Write-Host "  Unlabeled TBCC python (not matched above)" -ForegroundColor Yellow
    foreach ($pr in $orphan) {
      $cmd = [string]$pr.CommandLine
      if ($cmd.Length -gt 100) { $cmd = $cmd.Substring(0, 97) + "..." }
      Write-Host ("  PID {0,-7} {1}" -f $pr.ProcessId, $cmd) -ForegroundColor DarkYellow
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
  Write-Host "  - Use start.ps1 -Full -WtTabs so each service has a TBCC-* terminal tab title." -ForegroundColor DarkGray
  Write-Host "  - Tray: tbcc\tools\tbcc-supervisor.ps1 (per-service up/down)." -ForegroundColor DarkGray
  Write-Host "  - Logs: .tbcc-run\error-hub.log and TBCC-Errors tab." -ForegroundColor DarkGray
  Write-Host "  - Network per PID: resmon.exe -> Network tab -> sort Total (B/sec)." -ForegroundColor DarkGray
  Write-Host "  - Task Manager -> Details -> add Command line column." -ForegroundColor DarkGray
  Write-Host ""
}

if ($Watch) {
  if ($IntervalSec -lt 2) { $IntervalSec = 2 }
  while ($true) {
    Show-TbccProcessReport -Root $TbccRoot -FullStack:$Full
    Start-Sleep -Seconds $IntervalSec
  }
}

Show-TbccProcessReport -Root $TbccRoot -FullStack:$Full
