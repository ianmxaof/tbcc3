# Trim duplicate TBCC fat (extra supervisors, WT hosts, worker/tab wrappers) without full stack stop.
param(
  [string]$TbccRoot = "",
  [switch]$DryRun
)

$ErrorActionPreference = "Continue"
if (-not $TbccRoot) { $TbccRoot = Split-Path $PSScriptRoot -Parent }
. (Join-Path $PSScriptRoot "tbcc-service-control.ps1")
. (Join-Path $PSScriptRoot "tbcc-process-audit.ps1")
$hub = Join-Path $PSScriptRoot "tbcc-error-hub.ps1"
if (Test-Path -LiteralPath $hub) { . $hub }

$report = @{
  ok           = $true
  dry_run      = [bool]$DryRun
  supervisors  = @()
  wt_hosts     = @()
  workers      = @()
  tab_wrappers = @()
  orphan_cmd   = @()
  strays       = @()
}

function Invoke-TbccTrimKill {
  param([int]$ProcessId, [string]$Reason)
  if ($ProcessId -le 4) { return $false }
  if ($DryRun) { return $true }
  try {
    & taskkill.exe /PID $ProcessId /T /F 2>$null | Out-Null
    return $true
  } catch {
    try { Stop-Process -Id $ProcessId -Force -ErrorAction Stop; return $true } catch { return $false }
  }
}

# Test-TbccProcessTreeHasLiveWorker and Select-TbccTabWrapperKeepPid are provided by
# tbcc-service-control.ps1 (dot-sourced above) so the keep/kill decision is shared and
# unit-tested (see scripts/tests/trim-safety.Tests.ps1).

$all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
$exclude = @(Get-TbccStopExcludeProcessIds)

# 1) Duplicate tray supervisors — keep oldest root, drop the rest.
$supRoots = @($all | Where-Object {
    $_.CommandLine -and ([string]$_.CommandLine -match 'tbcc-supervisor\.ps1')
  } | Sort-Object { $_.CreationDate })
if ($supRoots.Count -gt 1) {
  $keepSup = [int]$supRoots[0].ProcessId
  foreach ($s in ($supRoots | Select-Object -Skip 1)) {
    $procId = [int]$s.ProcessId
    if ($exclude -contains $procId) { continue }
    $report.supervisors += @{ pid = $procId; action = $(if ($DryRun) { 'would_kill' } else { 'kill' }); reason = 'duplicate_supervisor' }
    if (-not $DryRun) { Invoke-TbccTrimKill -ProcessId $procId -Reason 'duplicate_supervisor' | Out-Null }
  }
  $report.supervisors = @(@{ kept = $keepSup; killed = ($supRoots.Count - 1) }) + $report.supervisors
  if (-not $DryRun) { Start-Sleep -Milliseconds 800; $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue) }
}

# 2) Extra Windows Terminal hosts — keep canonical pid file host.
$keepWt = Get-TbccWtHostPid -TbccRoot $TbccRoot
$wtHosts = @($all | Where-Object { [string]$_.Name -ieq 'WindowsTerminal.exe' })
foreach ($wt in $wtHosts) {
  $procId = [int]$wt.ProcessId
  if ($keepWt -and $procId -eq [int]$keepWt) { continue }
  if (-not (Test-TbccProcessTreeHasLiveWorker -RootPid $procId -AllProcesses $all)) {
    $report.wt_hosts += @{ pid = $procId; action = 'kill_stale'; reason = 'no_live_tbcc_workers' }
    if (-not $DryRun) { Invoke-TbccTrimKill -ProcessId $procId -Reason 'stale_wt' | Out-Null }
    continue
  }
  if ($keepWt -and (Test-TbccLiveWindowsTerminalPid -ProcessId $keepWt)) {
    continue
  }
  if (-not $keepWt) {
    $keepWt = $procId
    if (-not $DryRun) { Refresh-TbccWtHostPid -TbccRoot $TbccRoot -PreferredPid $procId }
  }
}

# 3) Duplicate python workers per service.
$trimReport = @(Ensure-TbccStackWorkersSingleton -TbccRoot $TbccRoot -FullStack -TrimOnly)
foreach ($row in $trimReport) {
  if ([int]$row.Trimmed -gt 0) {
    $report.workers += @{ service = $row.Title; trimmed = [int]$row.Trimmed; kept_pid = [int]$row.KeptPid }
  }
}

# 4) Duplicate run-tbcc-service tab wrappers — only when service has a live worker already.
#    Keep the wrapper whose tree still OWNS the live worker (not merely the newest),
#    so a taskkill /T never tears down the only live worker for the service.
if (Get-Command Get-TbccServiceTabWrapperProcesses -ErrorAction SilentlyContinue) {
  $services = Get-TbccStackServices -TbccRoot $TbccRoot -FullStack -MenuCatalog
  foreach ($svc in $services) {
    if (-not (Test-TbccServiceProcessRunning -Service $svc)) { continue }
    $wrappers = @(Get-TbccServiceTabWrapperProcesses -ServiceName $svc.Title -AllProcesses $all)
    if ($wrappers.Count -le 1) { continue }
    $annotated = @($wrappers | ForEach-Object {
        $procId = [int]$_.ProcessId
        [pscustomobject]@{
          Pid      = $procId
          Created  = $_.CreationDate
          OwnsLive = (Test-TbccProcessTreeHasLiveWorker -RootPid $procId -AllProcesses $all)
        }
      })
    $keepPid = Select-TbccTabWrapperKeepPid -Wrappers $annotated
    foreach ($w in $annotated) {
      if ($w.Pid -eq $keepPid) { continue }
      $report.tab_wrappers += @{ service = $svc.Title; pid = $w.Pid; owns_live = [bool]$w.OwnsLive; kept_pid = $keepPid }
      if (-not $DryRun) { Invoke-TbccTrimKill -ProcessId $w.Pid -Reason 'dup_tab_wrapper' | Out-Null }
    }
  }
}

# 5) Stale launcher/orchestrator cmd stubs only (duplicate tray cold-start shells).
$all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
foreach ($proc in ($all | Where-Object { [string]$_.Name -ieq 'cmd.exe' })) {
  $cmd = [string]$proc.CommandLine
  if ($cmd -notmatch 'Launch-TBCC|tbcc-cold-start|tbcc-orchestrate|tbcc-restart-full') { continue }
  $procId = [int]$proc.ProcessId
  $childCount = @($all | Where-Object { [int]$_.ParentProcessId -eq $procId }).Count
  if ($childCount -gt 0) { continue }
  $report.orphan_cmd += @{ pid = $procId; cmd = $cmd.Substring(0, [Math]::Min(90, $cmd.Length)) }
  if (-not $DryRun) { Invoke-TbccTrimKill -ProcessId $procId -Reason 'stale_launcher_cmd' | Out-Null }
}

# 6) Stray one-shots (OCI bootstrap, emoji httpx orphans).
$strayScript = Join-Path $PSScriptRoot "tbcc-kill-stray-processes.ps1"
if ((Test-Path -LiteralPath $strayScript) -and -not $DryRun) {
  try {
    $strayOut = & powershell -NoProfile -ExecutionPolicy Bypass -File $strayScript -TbccRoot $TbccRoot 2>$null
    if ($strayOut) { $report.strays = $strayOut | ConvertFrom-Json }
  } catch {}
}

# 7) Uvicorn reload orphans.
$cleanup = Join-Path $PSScriptRoot "tbcc-cleanup-orphans.ps1"
if ((Test-Path -LiteralPath $cleanup) -and -not $DryRun) {
  try { & powershell -NoProfile -ExecutionPolicy Bypass -File $cleanup 2>$null | Out-Null } catch {}
}

$audit = Get-TbccProcessAuditReport -Root $TbccRoot -FullStack
$report.audit = @{
  issue_count = [int]$audit.IssueCount
  summary     = [string]$audit.SummaryMicro
  dup_count   = [int]$audit.DupCount
  orphan_count = [int]$audit.OrphanCount
}
$report | ConvertTo-Json -Depth 6 -Compress
