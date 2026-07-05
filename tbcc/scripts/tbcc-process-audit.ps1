# TBCC process audit — shared by show-tbcc-processes.ps1, run-tbcc-stackwatch.ps1, orchestrator.
# Dot-source only; no side effects at load.
#
# Steady-state lean footprint (VPS-style always-on, 10 enabled services), for reference
# when reading audit/footprint output:
#   1  WindowsTerminal host (canonical pid in .tbcc-run\windows-terminal-host.pid)
#   ~10 python/py workers  (one per enabled service; node for dashboard/forum)
#   ~10-12 cmd.exe tab shells (one per WT tab; legitimate, do NOT trim as a group)
#   1  tbcc-supervisor.ps1 (a second = duplicate tray; trim keeps the oldest)
#   0  waste (duplicate workers, orphans, extra WT hosts/supervisors)
# See Show-TbccProcessFootprint in show-tbcc-processes.ps1 for the live one-line summary.

$script:TbccLeanForbiddenPatterns = @(
  @{ Title = "TBCC-MacroSearchBot"; Pattern = "bots\.macro_search_bot" },
  @{ Title = "TBCC-AdminBot"; Pattern = "bots\.admin_bot" },
  @{ Title = "AOF-Forum"; Pattern = "aof-forum" },
  @{ Title = "TBCC-NSFW-Detect"; Pattern = "run_nsfw_detect" },
  @{ Title = "TBCC-CLIP-Categorize"; Pattern = "run_clip_categorize" },
  @{ Title = "TBCC-Lustpress"; Pattern = "lustpress" }
)

$script:TbccProcessAuditExtraServices = @(
  # Watch organizer is in Get-TbccStackServices -MenuCatalog; keep empty unless we add non-menu sidecars.
)

function Test-TbccLeanProfile {
  param([string]$Root)
  $envPath = Join-Path $Root ".env"
  if (-not (Test-Path -LiteralPath $envPath)) { return $false }
  foreach ($line in Get-Content -LiteralPath $envPath -ErrorAction SilentlyContinue) {
    $t = $line.Trim()
    if ($t -match '^\s*TBCC_STACK_PROFILE\s*=\s*lean\s*$') { return $true }
  }
  return $false
}

function Get-TbccProcessAuditAllProcesses {
  if (Get-Command Get-TbccWin32ProcessListCached -ErrorAction SilentlyContinue) {
    return @(Get-TbccWin32ProcessListCached -MaxAgeSec 30)
  }
  @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
      $_.Name -match '^(python|py|node|bun|redis|postgres|com\.docker|wsl|WindowsTerminal|wt)\.exe$' -or $_.Name -eq 'vmmemWSL'
    })
}

function Get-TbccProcessAuditMatches {
  param([string]$Pattern, $All = $null)
  if (-not $All) { $All = Get-TbccProcessAuditAllProcesses }
  @($All | Where-Object { $_.CommandLine -and ($_.CommandLine -match $Pattern) })
}

function Get-TbccProcessAuditWorkerPids {
  <# Delegate to service-control leaf counter when available (py/cmd/node parent collapse). #>
  param($MatchedProcesses, $AllProcesses)
  if (Get-Command Get-TbccServiceWorkerLeafPids -ErrorAction SilentlyContinue) {
    return @(Get-TbccServiceWorkerLeafPids -MatchedProcesses $MatchedProcesses -AllProcesses $AllProcesses)
  }
  $pids = @($MatchedProcesses | ForEach-Object { [int]$_.ProcessId } | Select-Object -Unique)
  if ($pids.Count -le 1) { return $pids }
  $leaf = New-Object System.Collections.ArrayList
  foreach ($pr in $MatchedProcesses) {
    $procId = [int]$pr.ProcessId
    if ($leaf -contains $procId) { continue }
    $name = [string]$pr.Name
    if ($name -eq 'cmd.exe') {
      $anyKids = @($AllProcesses | Where-Object { $_.ParentProcessId -eq $procId })
      if ($anyKids.Count -gt 0) { continue }
    }
    if ($name -in @('py.exe', 'node.exe')) {
      $kids = @($AllProcesses | Where-Object { $_.ParentProcessId -eq $procId -and $pids -contains [int]$_.ProcessId })
      if ($kids.Count -gt 0) { continue }
    }
    [void]$leaf.Add($procId)
  }
  return @($leaf | Select-Object -Unique)
}

function Format-TbccProcessAuditRamMb {
  param([long]$Bytes)
  if ($Bytes -le 0) { return "-" }
  return ("{0:N0}" -f [math]::Round($Bytes / 1MB, 0))
}

function Get-TbccProcessAuditRamBytes {
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

function Get-TbccProcessAuditPortOwners {
  $rows = @()
  $ports = @(8000, 8001, 8002, 5173, 3000, 3001, 18789, 6379, 5432)
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
    if (-not $listen -and (Get-Command Test-TbccPortListening -ErrorAction SilentlyContinue)) {
      $listen = Test-TbccPortListening -Port $port
    }
    $rows += [pscustomobject]@{ Port = $port; Listening = $listen; Pids = ($pids -join ", ") }
  }
  return $rows
}

function Get-TbccProcessAuditReport {
  param(
    [Parameter(Mandatory = $true)][string]$Root,
    [switch]$FullStack
  )
  if (-not $PSBoundParameters.ContainsKey("FullStack")) { $FullStack = $true }
  if (-not (Get-Command Get-TbccStackServices -ErrorAction SilentlyContinue)) {
    . (Join-Path $PSScriptRoot "tbcc-service-control.ps1")
  }

  $issues = New-Object System.Collections.ArrayList
  $all = Get-TbccProcessAuditAllProcesses
  $services = @(Get-TbccStackServices -TbccRoot $Root -FullStack:$FullStack -MenuCatalog) + $script:TbccProcessAuditExtraServices
  $matchedPids = New-Object System.Collections.Generic.HashSet[int]
  $lean = Test-TbccLeanProfile -Root $Root
  $dupCount = 0
  $leanCount = 0
  $serviceRows = New-Object System.Collections.ArrayList

  foreach ($svc in $services) {
    $procs = @(Get-TbccProcessAuditMatches -Pattern $svc.CommandMatch -All $all)
    if ($matchedPids.Count -gt 0) {
      $procs = @($procs | Where-Object { -not $matchedPids.Contains([int]$_.ProcessId) })
    }
    $pids = @(Get-TbccProcessAuditWorkerPids -MatchedProcesses $procs -AllProcesses $all)
    foreach ($procId in $pids) { [void]$matchedPids.Add([int]$procId) }
    if ($pids.Count -gt 1) {
      $dupCount += ($pids.Count - 1)
      $dupMsg = "{0}: {1} duplicate processes (PIDs {2}) - stop extras or cold-start stack" -f $svc.Title, $pids.Count, ($pids -join ", ")
      [void]$issues.Add($dupMsg)
    }
    $ram = Get-TbccProcessAuditRamBytes -Pids $pids
    $status = if (Get-Command Test-TbccServiceProcessRunning -ErrorAction SilentlyContinue) {
      if (Test-TbccServiceProcessRunning -Service $svc) { "up" } else { "down" }
    } elseif ($pids.Count -gt 0) { "up" } else { "down" }
    [void]$serviceRows.Add([pscustomobject]@{
        Title        = $svc.Title
        Status       = $status
        PidCount     = $pids.Count
        Pids         = ($pids -join ", ")
        RamMb        = (Format-TbccProcessAuditRamMb $ram)
        Port         = $svc.Port
        CommandMatch = $svc.CommandMatch
      })
  }

  if ($lean) {
    foreach ($row in $script:TbccLeanForbiddenPatterns) {
      $procs = @(Get-TbccProcessAuditMatches -Pattern $row.Pattern -All $all)
      if ($procs.Count -eq 0) { continue }
      $leanCount += $procs.Count
      $pids = @($procs | Select-Object -ExpandProperty ProcessId -Unique) -join ", "
      $msg = "{0} running on lean profile (PID {1})" -f $row.Title, $pids
      [void]$issues.Add($msg)
    }
  }

  $tbccRootEsc = [regex]::Escape($Root)
  $orphanCount = 0
  $orphan = @($all | Where-Object {
      $_.Name -match '^(python|py)\.exe$' -and $_.CommandLine -and ($_.CommandLine -match $tbccRootEsc) -and -not ($matchedPids.Contains([int]$_.ProcessId))
    })
  foreach ($pr in $orphan) {
    $orphanCount++
    $cmd = [string]$pr.CommandLine
    if ($cmd.Length -gt 100) { $cmd = $cmd.Substring(0, 97) + "..." }
    [void]$issues.Add(("Orphan PID {0}: {1}" -f $pr.ProcessId, $cmd))
  }

  $parts = @()
  if ($dupCount -gt 0) { $parts += ("{0}dup" -f $dupCount) }
  if ($leanCount -gt 0) { $parts += ("{0}lean" -f $leanCount) }
  if ($orphanCount -gt 0) { $parts += ("{0}orph" -f $orphanCount) }
  $summaryMicro = if ($parts.Count) { $parts -join " " } else { "ok" }

  return [pscustomobject]@{
    At           = (Get-Date).ToString("o")
    Lean         = $lean
    Issues       = @($issues.ToArray())
    IssueCount   = $issues.Count
    DupCount     = $dupCount
    LeanCount    = $leanCount
    OrphanCount  = $orphanCount
    Summary      = if ($issues.Count) { ($parts -join " | ").ToUpper() } else { "OK" }
    SummaryMicro = $summaryMicro
    Services     = @($serviceRows.ToArray())
    Ports        = @(Get-TbccProcessAuditPortOwners)
  }
}

function Get-TbccProcessAuditSnapshotPath {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  Join-Path $TbccRoot ".tbcc-run\process-audit.json"
}

function Get-TbccProcessAuditAlertTokenPath {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  Join-Path $TbccRoot ".tbcc-run\process-audit-alert.token"
}

function Write-TbccProcessAuditSnapshot {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)]$Report,
    [string]$PreviousAlertToken = ""
  )
  $runDir = Join-Path $TbccRoot ".tbcc-run"
  if (-not (Test-Path -LiteralPath $runDir)) {
    New-Item -ItemType Directory -Path $runDir -Force | Out-Null
  }

  $issueSig = if ($Report.Issues.Count) {
    (($Report.Issues | ForEach-Object { [string]$_ }) | Sort-Object) -join "`n"
  } else { "" }

  $alertToken = $PreviousAlertToken
  if ($Report.IssueCount -gt 0) {
    $hash = [System.BitConverter]::ToString(
      [System.Security.Cryptography.SHA256]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($issueSig))
    ).Replace("-", "").Substring(0, 12).ToLower()
    if ($hash -ne $PreviousAlertToken) {
      $alertToken = $hash
      Set-Content -LiteralPath (Get-TbccProcessAuditAlertTokenPath -TbccRoot $TbccRoot) -Value $alertToken -Encoding ascii -NoNewline
    }
  } else {
    if (Test-Path -LiteralPath (Get-TbccProcessAuditAlertTokenPath -TbccRoot $TbccRoot)) {
      Remove-Item -LiteralPath (Get-TbccProcessAuditAlertTokenPath -TbccRoot $TbccRoot) -Force -ErrorAction SilentlyContinue
    }
    $alertToken = ""
  }

  $payload = @{
    at           = $Report.At
    lean         = [bool]$Report.Lean
    issueCount   = [int]$Report.IssueCount
    dupCount     = [int]$Report.DupCount
    leanCount    = [int]$Report.LeanCount
    orphanCount  = [int]$Report.OrphanCount
    summary      = [string]$Report.Summary
    summaryMicro = [string]$Report.SummaryMicro
    alertToken   = $alertToken
    issues       = @($Report.Issues)
  }
  $json = $payload | ConvertTo-Json -Depth 4 -Compress
  Set-Content -LiteralPath (Get-TbccProcessAuditSnapshotPath -TbccRoot $TbccRoot) -Value $json -Encoding UTF8
  return $alertToken
}

function Read-TbccProcessAuditSnapshot {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $path = Get-TbccProcessAuditSnapshotPath -TbccRoot $TbccRoot
  if (-not (Test-Path -LiteralPath $path)) { return $null }
  try {
    return (Get-Content -LiteralPath $path -Raw -ErrorAction Stop | ConvertFrom-Json)
  } catch {
    return $null
  }
}

function Invoke-TbccProcessAudit {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$Full,
    [switch]$LogIssues,
    [switch]$Quiet,
    [string]$Phase = ""
  )
  if (-not (Get-Command Write-TbccErrorHubEntry -ErrorAction SilentlyContinue)) {
    . (Join-Path $PSScriptRoot "tbcc-error-hub.ps1")
  }

  $fullStack = [bool]$Full
  if (-not $PSBoundParameters.ContainsKey("Full")) {
    $probe = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
      $_.CommandLine -match "celery_app|uvicorn app\.main"
    }
    if ($probe) { $fullStack = $true }
  }

  $report = Get-TbccProcessAuditReport -Root $TbccRoot -FullStack:$fullStack
  $prevToken = ""
  $tokenPath = Get-TbccProcessAuditAlertTokenPath -TbccRoot $TbccRoot
  if (Test-Path -LiteralPath $tokenPath) {
    $prevToken = [string](Get-Content -LiteralPath $tokenPath -Raw -ErrorAction SilentlyContinue).Trim()
  }
  $null = Write-TbccProcessAuditSnapshot -TbccRoot $TbccRoot -Report $report -PreviousAlertToken $prevToken

  if ($LogIssues -and $report.IssueCount -gt 0) {
    $phaseTag = if ($Phase) { " ($Phase)" } else { "" }
    foreach ($msg in $report.Issues) {
      Write-TbccErrorHubEntry -TbccRoot $TbccRoot -ServiceName "TBCC-ProcessAudit" -Level "WARN" -Message ($msg + $phaseTag)
    }
  }

  if (-not $Quiet) {
    $auditScript = Join-Path $PSScriptRoot "show-tbcc-processes.ps1"
    if (Test-Path -LiteralPath $auditScript) {
      & $auditScript -TbccRoot $TbccRoot -Full:$fullStack
    }
  } elseif ($Phase) {
    $color = if ($report.IssueCount -gt 0) { "Yellow" } else { "DarkGray" }
    Write-Host ("[audit{0}] {1} issue(s) - {2}" -f $(if ($Phase) { " $Phase" } else { "" }), $report.IssueCount, $report.SummaryMicro) -ForegroundColor $color
  }

  return $report
}
