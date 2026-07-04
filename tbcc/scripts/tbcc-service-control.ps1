# TBCC service control - stop/start/restart individual processes (tray supervisor + scripts).
# Dot-source from tbcc\tools\tbcc-supervisor.ps1

function Get-TbccLaunchPowerShellExe {
  $sys = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
  if (Test-Path -LiteralPath $sys) { return $sys }
  return "powershell.exe"
}

function Get-TbccControlPythonCmd {
  try {
    & py -3.13 -c "import sys" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { return "py -3.13" }
  } catch {}
  $py313 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"
  if (Test-Path -LiteralPath $py313) { return ('"' + $py313 + '"') }
  return "python"
}

function Set-TbccBackendRestartGrace {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [int]$Seconds = 0
  )
  $py = Get-TbccControlPythonCmd
  $backendDir = Join-Path $TbccRoot "backend"
  $script = Join-Path $backendDir "scripts\set_backend_restart_grace.py"
  if (-not (Test-Path -LiteralPath $script)) { return @{ ok = $false } }
  $args = @("--mark")
  if ($Seconds -gt 0) { $args += @("--seconds", [string]$Seconds) }
  $out = & $py $script @args 2>&1
  return @{ ok = ($LASTEXITCODE -eq 0); output = ($out | Out-String).Trim() }
}

function Clear-TbccBackendRestartGrace {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [int]$TailSeconds = -1
  )
  $py = Get-TbccControlPythonCmd
  $backendDir = Join-Path $TbccRoot "backend"
  $script = Join-Path $backendDir "scripts\set_backend_restart_grace.py"
  if (-not (Test-Path -LiteralPath $script)) { return @{ ok = $false } }
  $args = @("--clear")
  if ($TailSeconds -ge 0) { $args += @("--tail", [string]$TailSeconds) }
  $out = & $py $script @args 2>&1
  return @{ ok = ($LASTEXITCODE -eq 0); output = ($out | Out-String).Trim() }
}

function Wait-TbccBackendHealth {
  param(
    [string]$Url = "http://127.0.0.1:8000/health",
    [int]$TimeoutSec = 60
  )
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
      if ($r.StatusCode -eq 200) { return $true }
    } catch {}
    Start-Sleep -Seconds 1
  }
  return $false
}

$script:TbccWin32ProcessCache = $null
$script:TbccWin32ProcessCacheAt = $null

function Get-TbccWin32ProcessListCached {
  <# WMI full-process scan is expensive; share a short TTL cache for tray/panel/audit. #>
  param([int]$MaxAgeSec = 15)
  $now = Get-Date
  if (
    $script:TbccWin32ProcessCache -and $script:TbccWin32ProcessCacheAt -and
    (($now - $script:TbccWin32ProcessCacheAt).TotalSeconds -lt $MaxAgeSec)
  ) {
    return $script:TbccWin32ProcessCache
  }
  $script:TbccWin32ProcessCache = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
      $_.Name -match '^(python|py|node|bun|redis|postgres|com\.docker|wsl|WindowsTerminal|wt|cmd)\.exe$' -or
      $_.Name -eq 'vmmemWSL'
    })
  $script:TbccWin32ProcessCacheAt = $now
  return $script:TbccWin32ProcessCache
}

function Read-TbccControlDotEnv {
  param([string]$Path)
  $map = @{}
  if (-not (Test-Path -LiteralPath $Path)) { return $map }
  foreach ($line in Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue) {
    $t = $line.Trim()
    if (-not $t -or $t.StartsWith("#")) { continue }
    $eq = $t.IndexOf("=")
    if ($eq -lt 1) { continue }
    $k = $t.Substring(0, $eq).Trim()
    $v = $t.Substring($eq + 1).Trim()
    if ($v.StartsWith('"') -and $v.EndsWith('"') -and $v.Length -ge 2) { $v = $v.Substring(1, $v.Length - 2) }
    $map[$k] = $v
  }
  return $map
}

function Get-TbccStackProfile {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $dotEnv = Read-TbccControlDotEnv -Path (Join-Path $TbccRoot ".env")
  $raw = ($dotEnv['TBCC_STACK_PROFILE'] -as [string]).Trim().ToLower()
  if ($raw -eq 'full') { return 'full' }
  return 'lean'
}

function Set-TbccStackProfile {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][ValidateSet('lean', 'full')][string]$Profile
  )
  $envPath = Join-Path $TbccRoot ".env"
  $lines = @()
  if (Test-Path -LiteralPath $envPath) {
    $lines = @(Get-Content -LiteralPath $envPath -Encoding UTF8 -ErrorAction Stop)
  }
  $found = $false
  $out = New-Object System.Collections.ArrayList
  foreach ($line in $lines) {
    if ($line -match '^\s*#?\s*TBCC_STACK_PROFILE\s*=') {
      $found = $true
      [void]$out.Add('TBCC_STACK_PROFILE=' + $Profile)
      continue
    }
    [void]$out.Add($line)
  }
  if (-not $found) {
    [void]$out.Add('')
    [void]$out.Add('# Stack profile: lean (default) | full (Advanced tray start)')
    [void]$out.Add('TBCC_STACK_PROFILE=' + $Profile)
  }
  if ($lines.Count -gt 0 -or -not $found) {
    Set-Content -LiteralPath $envPath -Value ($out.ToArray()) -Encoding UTF8
  }
  return $Profile
}

function Get-TbccStackProfileLabel {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $p = Get-TbccStackProfile -TbccRoot $TbccRoot
  if ($p -eq 'lean') { return 'lean' }
  return 'full'
}

function Get-TbccTerminalWindowPrefs {
  <#
  Console buffer (mode con) and Windows Terminal pixel size for TBCC service tabs.
  Override in tbcc/.env: TBCC_CONSOLE_COLS, TBCC_CONSOLE_LINES, TBCC_WT_WINDOW_SIZE=width,height
  #>
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $dotEnv = Read-TbccControlDotEnv -Path (Join-Path $TbccRoot ".env")
  $cols = 84
  $lines = 24
  $wtW = 820
  $wtH = 460
  if ($dotEnv["TBCC_CONSOLE_COLS"]) {
    try { $cols = [int]$dotEnv["TBCC_CONSOLE_COLS"] } catch {}
  }
  if ($dotEnv["TBCC_CONSOLE_LINES"]) {
    try { $lines = [int]$dotEnv["TBCC_CONSOLE_LINES"] } catch {}
  }
  $sizeRaw = ""
  if ($dotEnv["TBCC_WT_WINDOW_SIZE"]) { $sizeRaw = "$($dotEnv['TBCC_WT_WINDOW_SIZE'])".Trim() }
  if ($sizeRaw -match '^(\d+)\s*,\s*(\d+)$') {
    $wtW = [int]$Matches[1]
    $wtH = [int]$Matches[2]
  } else {
    if ($dotEnv["TBCC_WT_WINDOW_WIDTH"]) {
      try { $wtW = [int]$dotEnv["TBCC_WT_WINDOW_WIDTH"] } catch {}
    }
    if ($dotEnv["TBCC_WT_WINDOW_HEIGHT"]) {
      try { $wtH = [int]$dotEnv["TBCC_WT_WINDOW_HEIGHT"] } catch {}
    }
  }
  $cols = [Math]::Max(40, [Math]::Min(200, $cols))
  $lines = [Math]::Max(12, [Math]::Min(60, $lines))
  $wtW = [Math]::Max(480, [Math]::Min(3840, $wtW))
  $wtH = [Math]::Max(320, [Math]::Min(2160, $wtH))
  return [pscustomobject]@{
    Cols     = $cols
    Lines    = $lines
    WtWidth  = $wtW
    WtHeight = $wtH
  }
}

function Test-TbccWtLaunchMinimized {
  <# New TBCC WT windows: minimized by default so cold start does not steal focus. TBCC_WT_LAUNCH_MINIMIZED=0 to disable. #>
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $raw = ($env:TBCC_WT_LAUNCH_MINIMIZED -as [string])
  if (-not $raw) {
    $dotEnv = Read-TbccControlDotEnv -Path (Join-Path $TbccRoot ".env")
    $raw = ($dotEnv['TBCC_WT_LAUNCH_MINIMIZED'] -as [string]).Trim()
  }
  if (-not $raw) { return $true }
  return $raw.Trim().ToLower() -notin @('0', 'false', 'no', 'off')
}

function Test-TbccBackgroundServiceStartEnabled {
  <# Auto-restarts (StackWatch, health remediate) run headless when no TBCC WT window exists. #>
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $dotEnv = Read-TbccControlDotEnv -Path (Join-Path $TbccRoot ".env")
  $raw = ($dotEnv['TBCC_BACKGROUND_SERVICE_START'] -as [string]).Trim().ToLower()
  if ($raw -match '^(0|false|no|off)$') { return $false }
  return $true
}

function Start-TbccStackServiceHeadless {
  param(
    [Parameter(Mandatory = $true)]$Service,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$UseErrorHubWrapper,
    [Parameter(Mandatory = $true)][string]$Command
  )
  if ($UseErrorHubWrapper) {
    $runner = Join-Path $TbccRoot "scripts\run-tbcc-service.ps1"
    if (-not (Test-Path -LiteralPath $runner)) { return $false }
    $null = Start-Process -FilePath "powershell.exe" -ArgumentList @(
      "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $runner,
      "-TbccRoot", $TbccRoot, "-ServiceName", $Service.Title
    ) -WindowStyle Hidden -PassThru
    return $true
  }
  $null = Start-Process -FilePath $env:ComSpec -ArgumentList @("/c", $Command) -WindowStyle Hidden -PassThru
  return $true
}

function Test-TbccControlLocalUrl {
  param([string]$Url)
  if (-not $Url) { return $false }
  try {
    $h = ([Uri]$Url).Host.ToLower()
    return ($h -eq "127.0.0.1" -or $h -eq "localhost")
  } catch { return $false }
}

function Stop-TbccListenersOnPort {
  param(
    [int]$Port,
    [int[]]$ExcludeProcessIds = @()
  )
  $killed = @()
  if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
    $pids = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($procId in $pids) {
      if ($procId -le 4) { continue }
      if ($ExcludeProcessIds -contains $procId) { continue }
      try { Stop-Process -Id $procId -Force -ErrorAction Stop; $killed += $procId } catch {}
    }
  }
  if ($killed.Count -eq 0) {
    $raw = netstat -ano 2>$null | Select-String (":$Port\s")
    foreach ($line in $raw) {
      if ($line -match '\s+(\d+)\s*$') {
        $procId = [int]$Matches[1]
        if ($procId -le 4) { continue }
        if ($ExcludeProcessIds -contains $procId) { continue }
        try { Stop-Process -Id $procId -Force -ErrorAction Stop; $killed += $procId } catch {}
      }
    }
  }
  return $killed
}

function Test-TbccProcessIsPowerShellEditorServices {
  param([string]$CommandLine)
  if (-not $CommandLine) { return $false }
  return ($CommandLine -match 'PowerShellEditorServices|Microsoft\.PowerShell\.EditorServices|PSES|Start-EditorServices')
}

function Test-TbccProcessIsIdeRootName {
  param([string]$ProcessName)
  if (-not $ProcessName) { return $false }
  $n = [string]$ProcessName
  if ($n -eq 'Cursor.exe' -or $n -eq 'Code.exe') { return $true }
  if ($n -like 'Cursor Helper*' -or $n -like 'Code Helper*') { return $true }
  return $false
}

function Get-TbccIdeProtectedProcessIds {
  <#
  Entire process trees rooted at Cursor / VS Code helpers — never kill during stack stop.
  Prevents "PowerShell Extension Terminal has stopped" when a stale TBCC pid file reuses an IDE pid.
  #>
  param($AllProcesses = $null)
  $protected = New-Object 'System.Collections.Generic.HashSet[int]'
  if (-not $AllProcesses) {
    $AllProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  }
  foreach ($pr in $AllProcesses) {
    $cmd = [string]$pr.CommandLine
    if (Test-TbccProcessIsPowerShellEditorServices -CommandLine $cmd) {
      [void]$protected.Add([int]$pr.ProcessId)
      foreach ($tp in (Get-TbccProcessTreePids -RootPid $pr.ProcessId -AllProcesses $AllProcesses)) {
        [void]$protected.Add([int]$tp)
      }
    }
    if (Test-TbccProcessIsIdeRootName -ProcessName $pr.Name) {
      foreach ($tp in (Get-TbccProcessTreePids -RootPid $pr.ProcessId -AllProcesses $AllProcesses)) {
        [void]$protected.Add([int]$tp)
      }
    }
  }
  return @($protected)
}

function Test-TbccProcessIsIdeShellHost {
  param(
    $Process,
    $AllProcesses = $null,
    $IdeProtected = $null
  )
  if (-not $Process) { return $false }
  if (-not $IdeProtected) {
    if (-not $AllProcesses) {
      $AllProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    }
    $IdeProtected = Get-TbccIdeProtectedProcessIds -AllProcesses $AllProcesses
  }
  return ($IdeProtected -contains [int]$Process.ProcessId)
}

function Test-TbccProcessIsTbccManagedShell {
  param([string]$CommandLine)
  if (-not $CommandLine) { return $false }
  if (Test-TbccProcessIsPowerShellEditorServices -CommandLine $CommandLine) { return $false }
  if ($CommandLine -match 'title\s+"(TBCC-|AOF-Forum)') { return $true }
  if ($CommandLine -match 'run-tbcc-service\.ps1') { return $true }
  if ($CommandLine -match 'run-tbcc-orchestrator\.ps1|tbcc-orchestrate\.ps1') { return $true }
  if ($CommandLine -match 'tbcc-error-hub\.ps1|show-tbcc-error-hub') { return $true }
  if ($CommandLine -match 'run-tbcc-stackwatch\.ps1|show-tbcc-processes\.ps1') { return $true }
  if ($CommandLine -match 'tbcc-stop-full-stack\.ps1|tbcc-cold-start\.ps1|tbcc-restart-full-stack\.ps1') { return $true }
  return $false
}

function Stop-TbccStrayStackProcesses {
  <#
  Final sweep: kill all TBCC python/node workers under the repo root (duplicates, orphans, lean violations).
  #>
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [int[]]$ExcludeProcessIds = @()
  )
  $exclude = @(Get-TbccStopExcludeProcessIds -Extra $ExcludeProcessIds)
  $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  $esc = [regex]::Escape($TbccRoot)
  $killed = @()

  $pyPatterns = @(
    'uvicorn\s+app\.main',
    'celery\s+-A\s+app\.workers',
    'app\.workers\.celery_app',
        'bots\.(payment_bot|loot_bot|secretary_bot|companion_bot|macro_search_bot|album_composer_bot|llm_chat_bot)',
    'run_nsfw_detect',
    'run_clip_categorize',
    'lustpress',
    'watch_folder_organizer',
    'show-tbcc-processes\.ps1',
    'run-tbcc-stackwatch\.ps1'
  )

  foreach ($pr in $all) {
    if ($exclude -contains [int]$pr.ProcessId) { continue }
    $cmd = [string]$pr.CommandLine
    if (-not $cmd -or $cmd -notmatch $esc) { continue }
    $name = [string]$pr.Name
    $match = $false
    if ($name -match '^(python|py)\.exe$') {
      foreach ($pat in $pyPatterns) {
        if ($cmd -match $pat) { $match = $true; break }
      }
      if (-not $match -and $cmd -match ($esc + '\\backend\\')) { $match = $true }
    } elseif ($name -eq 'node.exe' -and (
        ($cmd -match ($esc + '\\dashboard\\') -and $cmd -match 'vite|npm') -or
        ($cmd -match 'aof-forum' -and $cmd -match 'next dev|next-server')
      )) {
      $match = $true
    } elseif ($name -eq 'bun.exe' -and $cmd -match ($esc + '\\')) {
      $match = $true
    }
    if (-not $match) { continue }
    if (Test-TbccProcessIsIdeShellHost -Process $pr -AllProcesses $all -IdeProtected $exclude) { continue }
    $n = Stop-TbccProcessTree -ProcessId $pr.ProcessId -ExcludeProcessIds $exclude -AllProcesses $all
    if ($n -gt 0) { $killed += [int]$pr.ProcessId }
  }
  return @($killed | Select-Object -Unique)
}

function Test-TbccProcessIsTbccWtHost {
  param($Process)
  if (-not $Process) { return $false }
  $name = [string]$Process.Name
  if ($name -notin @('wt.exe', 'WindowsTerminal.exe')) { return $false }
  $cmd = [string]$Process.CommandLine
  return ($cmd -match '--title\s+(TBCC-|AOF-Forum)|new-tab.*TBCC-|TBCC-Backend|TBCC-Errors')
}

function Get-TbccStopExcludeProcessIds {
  param([int[]]$Extra = @())
  $ids = @($Extra) + @(Get-TbccSupervisorProcessIds) | Select-Object -Unique
  try {
    $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $ids += @(Get-TbccIdeProtectedProcessIds -AllProcesses $all)
  } catch {}
  return @($ids | Select-Object -Unique)
}

function Stop-TbccProcessesByCommandMatch {
  param(
    [string]$Pattern,
    [int[]]$ExcludeProcessIds = @()
  )
  $killed = @()
  try {
    $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $procs = $all | Where-Object { $_.CommandLine -and ($_.CommandLine -match $Pattern) }
    foreach ($pr in $procs) {
      if ($ExcludeProcessIds -contains $pr.ProcessId) { continue }
      if (Test-TbccProcessIsIdeShellHost -Process $pr -AllProcesses $all) { continue }
      try { Stop-Process -Id $pr.ProcessId -Force -ErrorAction Stop; $killed += $pr.ProcessId } catch {}
    }
  } catch {}
  return $killed
}

function Stop-TbccProcessesByServiceTitle {
  param(
    [string]$Title,
    [string]$TbccRoot,
    [switch]$GracefulTabClose,
    [int]$TabWaitSeconds = 12
  )
  $killed = @()
  $pat = 'run-tbcc-service\.ps1.*-ServiceName\s+' + [regex]::Escape($Title)
  $pat2 = 'run-tbcc-service\.ps1.*-ServiceName\s+' + [regex]::Escape('"' + $Title + '"')
  $pat3 = 'title\s+"' + [regex]::Escape($Title) + '"'

  if ($GracefulTabClose) {
    $killed += @(Stop-TbccProcessesByCommandMatch -Pattern $pat3)
    $deadline = (Get-Date).AddSeconds($TabWaitSeconds)
    while ((Get-Date) -lt $deadline) {
      $wrappers = @()
      if (Get-Command Get-TbccServiceTabWrapperProcesses -ErrorAction SilentlyContinue) {
        $wrappers = @(Get-TbccServiceTabWrapperProcesses -ServiceName $Title)
      } else {
        $hub = Join-Path $TbccRoot "scripts\tbcc-error-hub.ps1"
        if (Test-Path -LiteralPath $hub) {
          . $hub
          $wrappers = @(Get-TbccServiceTabWrapperProcesses -ServiceName $Title)
        }
      }
      if ($wrappers.Count -eq 0) { break }
      Start-Sleep -Milliseconds 250
    }
  } else {
    $killed += @(Stop-TbccProcessesByCommandMatch -Pattern $pat)
    $killed += @(Stop-TbccProcessesByCommandMatch -Pattern $pat2)
    $killed += @(Stop-TbccProcessesByCommandMatch -Pattern $pat3)
  }

  $wrappersLeft = @()
  if (Get-Command Get-TbccServiceTabWrapperProcesses -ErrorAction SilentlyContinue) {
    $wrappersLeft = @(Get-TbccServiceTabWrapperProcesses -ServiceName $Title)
  }
  if ($wrappersLeft.Count -gt 0) {
    $killed += @(Stop-TbccProcessesByCommandMatch -Pattern $pat)
    $killed += @(Stop-TbccProcessesByCommandMatch -Pattern $pat2)
  }

  if ($TbccRoot -and (Get-Command Invoke-TbccCloseServiceTab -ErrorAction SilentlyContinue)) {
    Start-Sleep -Milliseconds 200
    $null = Invoke-TbccCloseServiceTab -TbccRoot $TbccRoot -ServiceName $Title
  } elseif ($TbccRoot) {
    $hub = Join-Path $TbccRoot "scripts\tbcc-error-hub.ps1"
    if (Test-Path -LiteralPath $hub) {
      . $hub
      Start-Sleep -Milliseconds 200
      $null = Invoke-TbccCloseServiceTab -TbccRoot $TbccRoot -ServiceName $Title
    }
  }
  return @($killed | Select-Object -Unique)
}

$script:TbccMandatoryServiceIds = @('album_composer')
$script:TbccLeanDefaultOffServiceIds = @('llm_chat', 'watch', 'forum', 'macro_search', 'admin', 'companion')
$script:TbccFullDefaultOffServiceIds = @('llm_chat', 'watch', 'forum')

function Get-TbccOpenClawGatewayPort {
  param($DotEnv = $null)
  $raw = if ($DotEnv) { $DotEnv['TBCC_OPENCLAW_GATEWAY_PORT'] } else { $null }
  if (-not $raw) { $raw = $env:TBCC_OPENCLAW_GATEWAY_PORT }
  if ($raw -and ($raw -as [string]).Trim() -match '^\d+$') {
    return [int]($raw -as [string]).Trim()
  }
  return 18789
}

function Test-TbccOpenClawCliInstalled {
  if (Get-Command openclaw -ErrorAction SilentlyContinue) { return $true }
  if (Test-Path -LiteralPath (Join-Path $env:USERPROFILE ".openclaw\gateway.cmd")) { return $true }
  return Test-Path -LiteralPath (Join-Path $env:APPDATA "npm\node_modules\openclaw\dist\index.js")
}

function Test-TbccOpenClawAutoStartEnabled {
  param($DotEnv = $null)
  $raw = if ($DotEnv) { $DotEnv['TBCC_OPENCLAW_AUTO_START'] } else { $null }
  if (-not $raw) { $raw = $env:TBCC_OPENCLAW_AUTO_START }
  if (-not $raw) { return $true }
  return (($raw -as [string]).Trim().ToLower() -match '^(1|true|yes|on)$')
}

function Test-TbccOpenClawConfigured {
  $cfg = Join-Path $env:USERPROFILE ".openclaw"
  if (Test-Path -LiteralPath $cfg) { return $true }
  if (-not (Test-TbccOpenClawCliInstalled)) { return $false }
  try {
    & openclaw config get gateway.port 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
  } catch {
    return $false
  }
}

function Get-TbccOpenClawGatewayLaunchCmd {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $runScript = Join-Path $TbccRoot "scripts\run-openclaw-gateway.ps1"
  return 'powershell -NoProfile -ExecutionPolicy Bypass -File "' + $runScript + '" -TbccRoot "' + $TbccRoot + '"'
}

function Get-TbccOpenClawGatewayCommandMatch {
  return '(?i)run-openclaw-gateway\.ps1|node_modules[/\\]openclaw[/\\].*\bgateway\b|\.openclaw[/\\]gateway\.cmd|openclaw(\.cmd)?\s+gateway'
}

function Stop-TbccOpenClawGatewaySurfaces {
  <#
  Kill TBCC-managed OpenClaw gateway (WT tab, run-openclaw-gateway.ps1, node on :18789).
  Does not stop the separate Windows Scheduled Task "OpenClaw Gateway" from openclaw onboard.
  #>
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [int[]]$ExcludeProcessIds = @()
  )
  $dotEnv = Read-TbccControlDotEnv -Path (Join-Path $TbccRoot ".env")
  if (-not (Test-TbccOpenClawAutoStartEnabled -DotEnv $dotEnv)) { return @() }
  $port = Get-TbccOpenClawGatewayPort -DotEnv $dotEnv
  $killed = @()
  foreach ($pat in @(Get-TbccOpenClawGatewayCommandMatch)) {
    $killed += @(Stop-TbccProcessesByCommandMatch -Pattern $pat -ExcludeProcessIds $ExcludeProcessIds)
  }
  $killed += @(Stop-TbccListenersOnPort -Port $port -ExcludeProcessIds $ExcludeProcessIds)
  if ($TbccRoot) {
    $killed += @(Stop-TbccProcessesByServiceTitle -Title "OpenClaw-Gateway" -TbccRoot $TbccRoot)
  }
  return @($killed | Select-Object -Unique)
}

function Get-TbccStackServiceById {
  param(
    [Parameter(Mandatory = $true)][string]$ServiceId,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [switch]$MenuCatalog
  )
  return @(Get-TbccStackServices -TbccRoot $TbccRoot -FullStack:$FullStack -MenuCatalog:$MenuCatalog |
    Where-Object { $_.Id -eq $ServiceId } | Select-Object -First 1)
}

function Get-TbccStackServices {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [switch]$MenuCatalog
  )
  $py = Get-TbccControlPythonCmd
  $backendDir = Join-Path $TbccRoot "backend"
  $dashboardDir = Join-Path $TbccRoot "dashboard"
  $aofForumDir = Join-Path (Split-Path $TbccRoot -Parent) "aof-forum"
  $dashMatch = '(?i)' + [regex]::Escape($dashboardDir) + '.*(vite|npm run dev|npm\.cmd)'
  $forumMatch = '(?i)' + [regex]::Escape($aofForumDir) + '.*(next dev|next-server|npm run dev|npm\.cmd)'
  $servicesDir = Join-Path $TbccRoot "services"
  $hasForum = Test-Path (Join-Path $aofForumDir "package.json")
  $dotEnv = Read-TbccControlDotEnv -Path (Join-Path $TbccRoot ".env")
  $stackProfile = ($dotEnv['TBCC_STACK_PROFILE'] -as [string]).Trim().ToLower()
  $leanStack = $stackProfile -eq 'lean'

  # Match start.ps1: no --reload unless TBCC_UVICORN_RELOAD=1 in .env (avoids orphan workers on Windows).
  $uvicornReload = ''
  if ($dotEnv['TBCC_UVICORN_RELOAD'] -match '^(1|true|yes)$') {
    $uvicornReload = ' --reload --reload-exclude scripts --reload-delay 1'
  }
  $list = New-Object System.Collections.ArrayList

  [void]$list.Add([pscustomobject]@{
      Id = "backend"; Title = "TBCC-Backend"; Port = 8000; CommandMatch = "uvicorn app\.main:app";
      Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m uvicorn app.main:app --host 127.0.0.1 --port 8000' + $uvicornReload)
    })
  [void]$list.Add([pscustomobject]@{
      Id = "dashboard"; Title = "TBCC-Dashboard"; Port = 5173; CommandMatch = $dashMatch;
      Command = ('cd /d "' + $dashboardDir + '" & npm run dev')
    })
  if ($hasForum -and (-not $leanStack -or $MenuCatalog)) {
    [void]$list.Add([pscustomobject]@{
        Id = "forum"; Title = "AOF-Forum"; Port = 3001; CommandMatch = $forumMatch;
        Command = ('cd /d "' + $aofForumDir + '" & npm run dev')
      })
  }

  $celeryHomeQueues = ($dotEnv['TBCC_CELERY_HOME_QUEUES'] -as [string]).Trim()
  if (-not $celeryHomeQueues) { $celeryHomeQueues = 'celery,scrape,subscription,telegram' }

  if ($FullStack) {
    [void]$list.Add([pscustomobject]@{
        Id = "celery"; Title = "TBCC-Celery"; Port = 0; CommandMatch = "app\.workers\.celery_app worker.*-Q celery";
        Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m celery -A app.workers.celery_app worker -l info -P solo -Q ' + $celeryHomeQueues)
      })
    [void]$list.Add([pscustomobject]@{
        Id = "celery_post"; Title = "TBCC-Celery-Post"; Port = 0; CommandMatch = "app\.workers\.celery_app worker.*-Q post -n post@";
        Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m celery -A app.workers.celery_app worker -l info -P solo -Q post -n post@%h')
      })
    [void]$list.Add([pscustomobject]@{
        Id = "celery_post_scheduler"; Title = "TBCC-Celery-Post-Scheduler"; Port = 0; CommandMatch = "app\.workers\.celery_app worker.*-Q post_scheduler";
        Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m celery -A app.workers.celery_app worker -l info -P solo -Q post_scheduler -n scheduler@%h')
      })
    [void]$list.Add([pscustomobject]@{
        Id = "beat"; Title = "TBCC-Beat"; Port = 0; CommandMatch = "app\.workers\.celery_app beat";
        Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m celery -A app.workers.celery_app beat -l info')
      })
    [void]$list.Add([pscustomobject]@{
        Id = "payment"; Title = "TBCC-PaymentBot"; Port = 0; CommandMatch = "bots\.payment_bot";
        Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m bots.payment_bot')
      })
    [void]$list.Add([pscustomobject]@{
        Id = "secretary"; Title = "TBCC-SecretaryBot"; Port = 0; CommandMatch = "bots\.secretary_bot";
        Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m bots.secretary_bot')
      })
    if (-not $leanStack -or $MenuCatalog) {
      [void]$list.Add([pscustomobject]@{
          Id = "companion"; Title = "TBCC-CompanionBot"; MenuLabel = "TBCC-CompanionBot (spicy)";
          Port = 0; CommandMatch = "bots\.companion_bot";
          Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m bots.companion_bot')
        })
      [void]$list.Add([pscustomobject]@{
          Id = "admin"; Title = "TBCC-AdminBot"; MenuLabel = "TBCC-AdminBot (Storage /erome)";
          Port = 0; CommandMatch = "bots\.admin_bot";
          Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m bots.admin_bot')
        })
    }
    if (-not $leanStack -or $MenuCatalog) {
      [void]$list.Add([pscustomobject]@{
          Id = "macro_search"; Title = "TBCC-MacroSearchBot"; Port = 0; CommandMatch = "bots\.macro_search_bot";
          Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m bots.macro_search_bot')
        })
    }
    [void]$list.Add([pscustomobject]@{
        Id = "loot"; Title = "TBCC-LootBot"; Port = 0; CommandMatch = "bots\.loot_bot";
        Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m bots.loot_bot')
      })
    [void]$list.Add([pscustomobject]@{
        Id = "album_composer"; Title = "TBCC-AlbumComposer"; MenuLabel = "TBCC-AlbumComposer (remixer)";
        Port = 0; CommandMatch = "bots\.album_composer_bot";
        Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m bots.album_composer_bot')
      })
    if ((Test-TbccOpenClawAutoStartEnabled -DotEnv $dotEnv) -and (Test-TbccOpenClawCliInstalled)) {
      $ocPort = Get-TbccOpenClawGatewayPort -DotEnv $dotEnv
      $runOc = Join-Path $TbccRoot "scripts\run-openclaw-gateway.ps1"
      [void]$list.Add([pscustomobject]@{
          Id = "openclaw"; Title = "OpenClaw-Gateway"; Port = $ocPort;
          CommandMatch = (Get-TbccOpenClawGatewayCommandMatch);
          Command = ('powershell -NoProfile -ExecutionPolicy Bypass -File "' + $runOc + '" -TbccRoot "' + $TbccRoot + '"')
        })
    }
    if ($MenuCatalog) {
      [void]$list.Add([pscustomobject]@{
          Id = "llm_chat"; Title = "TBCC-LlmChatBot"; Port = 0; CommandMatch = "bots\.llm_chat_bot";
          Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m bots.llm_chat_bot')
        })
      [void]$list.Add([pscustomobject]@{
          Id = "watch"; Title = "TBCC-WatchOrganizer"; Port = 0; CommandMatch = "watch_folder_organizer";
          Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m app.services.watch_folder_organizer')
        })
    }
  }

  $skipEnrichment = (-not $MenuCatalog) -and (
    $leanStack -or (($dotEnv['TBCC_SKIP_ENRICHMENT'] -as [string]).Trim().ToLower() -match '^(1|true|yes)$')
  )
  $nsfwUrl = $dotEnv["TBCC_NSFW_DETECT_URL"]
  $nsfwOk = $MenuCatalog -or ((Test-TbccControlLocalUrl $nsfwUrl) -and -not $skipEnrichment)
  if ($nsfwOk -and (Test-Path (Join-Path $servicesDir "run_nsfw_detect.py"))) {
    [void]$list.Add([pscustomobject]@{
        Id = "nsfw"; Title = "TBCC-NSFW-Detect"; Port = 8001; CommandMatch = "run_nsfw_detect";
        Command = ('cd /d "' + $servicesDir + '" & ' + $py + ' run_nsfw_detect.py')
      })
  }

  $lustUrl = $dotEnv["TBCC_LUSTPRESS_URL"]
  $lustDir = Join-Path $servicesDir "lustpress"
  $lustOk = $MenuCatalog -or ((Test-TbccControlLocalUrl $lustUrl) -and -not $skipEnrichment)
  if ($lustOk -and (Test-Path (Join-Path $lustDir "package.json"))) {
    $bun = $null
    try { $bun = (Get-Command "bun" -ErrorAction Stop).Source } catch {}
    if (-not $bun) {
      $bun = Join-Path $env:USERPROFILE ".bun\bin\bun.exe"
    }
    if ($bun -and (Test-Path -LiteralPath $bun)) {
      $bunQ = '"' + $bun + '"'
      [void]$list.Add([pscustomobject]@{
          Id = "lustpress"; Title = "TBCC-Lustpress"; Port = 3000; CommandMatch = "lustpress[\\/].*\bbun\b|\bbun\.exe\b run start:(dev|prod)";
          Command = ('cd /d "' + $lustDir + '" & ' + $bunQ + ' run start:dev')
        })
    }
  }

  $clipUrl = $dotEnv["TBCC_CLIP_CATEGORIZE_URL"]
  $clipCats = $dotEnv["TBCC_CLIP_CATEGORIES_FILE"]
  $clipOk = $MenuCatalog -or ((Test-TbccControlLocalUrl $clipUrl) -and -not $skipEnrichment)
  if ($clipOk -and (Test-Path (Join-Path $servicesDir "run_clip_categorize.py"))) {
    if ($MenuCatalog -or ($clipCats -and (Test-Path -LiteralPath $clipCats))) {
      [void]$list.Add([pscustomobject]@{
          Id = "clip"; Title = "TBCC-CLIP-Categorize"; Port = 8002; CommandMatch = "run_clip_categorize";
          Command = ('cd /d "' + $servicesDir + '" & ' + $py + ' run_clip_categorize.py')
        })
    }
  }

  $launcherDir = Join-Path $TbccRoot ".tbcc-run\launchers"
  if (Test-Path -LiteralPath $launcherDir) {
    foreach ($svc in $list) {
      $safe = ($svc.Title -replace '[^\w\-]', '_')
      $lf = Join-Path $launcherDir ($safe + ".json")
      if (Test-Path -LiteralPath $lf) {
        try {
          $meta = Get-Content -LiteralPath $lf -Raw -Encoding UTF8 | ConvertFrom-Json
          if ($meta.command) { $svc | Add-Member -NotePropertyName Command -NotePropertyValue ([string]$meta.command) -Force }
        } catch {}
      }
    }
  }

  return @($list.ToArray())
}

function Get-TbccListeningPortSet {
  <# One netstat pass for supervisor status cache (avoids N separate shell calls). #>
  $ports = New-Object 'System.Collections.Generic.HashSet[int]'
  $lines = @(netstat -ano 2>$null)
  foreach ($line in $lines) {
    if ($line -notmatch 'LISTENING') { continue }
    if ($line -match ':(\d+)\s+.*LISTENING') {
      try { [void]$ports.Add([int]$Matches[1]) } catch {}
    }
  }
  return $ports
}

function Test-TbccPortListening {
  param(
    [int]$Port,
    $ListeningPorts = $null
  )
  if ($Port -le 0) { return $false }
  if ($null -ne $ListeningPorts) {
    return $ListeningPorts.Contains($Port)
  }
  if (netstat -ano 2>$null | Select-String -Pattern ":\s*$Port\s+.*LISTENING") { return $true }
  try {
    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
      return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    }
  } catch {}
  return $false
}

function Test-TbccServiceProcessRunning {
  param(
    $Service,
    $ListeningPorts = $null,
    $AllProcesses = $null
  )
  if ($Service.Port -gt 0 -and (Test-TbccPortListening -Port $Service.Port -ListeningPorts $ListeningPorts)) {
    return $true
  }
  if (-not $Service.CommandMatch) { return $false }
  if (-not $AllProcesses) {
    $AllProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  }
  $alive = @($AllProcesses | Where-Object { $_.CommandLine -and ($_.CommandLine -match $Service.CommandMatch) })
  return ($alive.Count -gt 0)
}

function Get-TbccServiceWorkerLeafPids {
  <# py.exe launcher + python.exe child = one worker; count leaf PIDs only. #>
  param(
    $MatchedProcesses,
    $AllProcesses
  )
  $pids = @($MatchedProcesses | ForEach-Object { [int]$_.ProcessId } | Select-Object -Unique)
  if ($pids.Count -le 1) { return $pids }
  $leaf = New-Object System.Collections.ArrayList
  foreach ($pr in $MatchedProcesses) {
    $procId = [int]$pr.ProcessId
    if ($leaf -contains $procId) { continue }
    $name = [string]$pr.Name
    if ($name -eq 'cmd.exe') {
      # npm/vite wrappers: child may not match CommandMatch (e.g. npm.cmd) — skip any cmd with children.
      $anyKids = @($AllProcesses | Where-Object { $_.ParentProcessId -eq $procId })
      if ($anyKids.Count -gt 0) { continue }
    }
    if ($name -eq 'py.exe') {
      $kids = @($AllProcesses | Where-Object { $_.ParentProcessId -eq $procId -and $pids -contains [int]$_.ProcessId })
      if ($kids.Count -gt 0) { continue }
    }
    if ($name -eq 'node.exe') {
      $kids = @($AllProcesses | Where-Object { $_.ParentProcessId -eq $procId -and $pids -contains [int]$_.ProcessId })
      if ($kids.Count -gt 0) { continue }
    }
    [void]$leaf.Add($procId)
  }
  return @($leaf | Select-Object -Unique)
}

function Get-TbccServiceWorkerProcesses {
  param(
    $Service,
    $AllProcesses = $null
  )
  if (-not $Service.CommandMatch) { return @() }
  if (-not $AllProcesses) {
    $AllProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  }
  $matched = @($AllProcesses | Where-Object { $_.CommandLine -and ($_.CommandLine -match $Service.CommandMatch) })
  $leafPids = @(Get-TbccServiceWorkerLeafPids -MatchedProcesses $matched -AllProcesses $AllProcesses)
  if ($leafPids.Count -eq 0) { return @() }
  return @($AllProcesses | Where-Object { $leafPids -contains [int]$_.ProcessId })
}

function Stop-TbccServiceWorkerDuplicates {
  <# Keep one worker (newest); kill older copies and py.exe launcher trees. #>
  param(
    [Parameter(Mandatory = $true)]$Service,
    [int[]]$ExcludeProcessIds = @()
  )
  $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  $workers = @(Get-TbccServiceWorkerProcesses -Service $Service -AllProcesses $all)
  if ($workers.Count -le 1) { return @() }
  $sorted = @($workers | Sort-Object { $_.CreationDate } -Descending)
  $keep = [int]$sorted[0].ProcessId
  $killed = @()
  foreach ($w in $sorted | Select-Object -Skip 1) {
    $workerPid = [int]$w.ProcessId
    if ($ExcludeProcessIds -contains $workerPid) { continue }
    $n = Stop-TbccProcessTree -ProcessId $workerPid -ExcludeProcessIds $ExcludeProcessIds -AllProcesses $all
    if ($n -gt 0) { $killed += $workerPid }
  }
  # Orphan py.exe launcher (child python already dead).
  $pat = 'py\.exe.*' + $Service.CommandMatch
  $killed += @(Stop-TbccProcessesByCommandMatch -Pattern $pat -ExcludeProcessIds $ExcludeProcessIds)
  return @($killed | Select-Object -Unique)
}

function Get-TbccSchedulingStackServices {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack
  )
  $full = $true
  if ($PSBoundParameters.ContainsKey('FullStack')) { $full = [bool]$FullStack }
  return @(
    Get-TbccStackServices -TbccRoot $TbccRoot -FullStack:$full |
      Where-Object { $_.Id -in @('beat', 'celery', 'celery_post', 'celery_post_scheduler') }
  )
}

function Clear-TbccSchedulingWorkersBeforeLaunch {
  <#
  Kill every Beat / Celery / Celery-Post worker before opening fresh WT tabs.
  Prevents duplicate workers when prior tabs closed slowly or restarts stack on the same window.
  #>
  param([int]$SettleMs = 600)
  $patterns = @(
    'app\.workers\.celery_app beat',
    'app\.workers\.celery_app worker.*-Q\s+celery',
    'app\.workers\.celery_app worker.*-Q\s+post'
  )
  $killed = @()
  foreach ($pat in $patterns) {
    $killed += @(Stop-TbccProcessesByCommandMatch -Pattern $pat)
    $killed += @(Stop-TbccProcessesByCommandMatch -Pattern ('py\.exe.*' + $pat))
  }
  $killed = @($killed | Select-Object -Unique)
  if ($killed.Count -gt 0 -and $SettleMs -gt 0) {
    Start-Sleep -Milliseconds $SettleMs
  }
  return $killed.Count
}

function Test-TbccServiceWrapperStarting {
  param([Parameter(Mandatory = $true)][string]$Title)
  if (-not (Get-Command Get-TbccProcessAuditMatches -ErrorAction SilentlyContinue)) { return $false }
  $esc = [regex]::Escape($Title)
  $pat = 'run-tbcc-service\.ps1.*-ServiceName\s+("?' + $esc + '"?)'
  return @(Get-TbccProcessAuditMatches -Pattern $pat).Count -gt 0
}

function Ensure-TbccStackWorkersSingleton {
  <#
  Trim to one worker per stack service (bots, backend workers, Celery, etc.).
  Restarts any that are missing when TbccRoot is provided (unless -TrimOnly).
  #>
  param(
    [string]$TbccRoot = "",
    [switch]$FullStack,
    [switch]$TrimOnly,
    [string[]]$ServiceIds = @()
  )
  $report = @()
  $services = @()
  if ($TbccRoot) {
    $services = @(Get-TbccStackServices -TbccRoot $TbccRoot -FullStack:$FullStack)
  }
  if ($ServiceIds.Count -gt 0) {
    $services = @($services | Where-Object { $_.Id -in $ServiceIds })
  }
  if ($services.Count -eq 0) {
    $services = @(
      [pscustomobject]@{ Id = "beat"; Title = "TBCC-Beat"; CommandMatch = 'app\.workers\.celery_app beat' },
      [pscustomobject]@{ Id = "celery"; Title = "TBCC-Celery"; CommandMatch = 'app\.workers\.celery_app worker.*-Q\s+celery' },
      [pscustomobject]@{ Id = "celery_post"; Title = "TBCC-Celery-Post"; CommandMatch = 'app\.workers\.celery_app worker.*-Q\s+post' }
    )
  }
  foreach ($svc in $services) {
    if (-not $svc.CommandMatch) { continue }
    $trimmed = @(Stop-TbccServiceWorkerDuplicates -Service $svc)
    $remaining = @(Get-TbccServiceWorkerProcesses -Service $svc)
    $kept = if ($remaining.Count -gt 0) { [int]$remaining[0].ProcessId } else { 0 }
    if ($remaining.Count -gt 1) {
      $null = Stop-TbccServiceWorkerDuplicates -Service $svc
      $remaining = @(Get-TbccServiceWorkerProcesses -Service $svc)
      $kept = if ($remaining.Count -gt 0) { [int]$remaining[0].ProcessId } else { 0 }
    }
    $restarted = $false
    if (-not $TrimOnly -and $kept -eq 0 -and $TbccRoot -and $svc.Command) {
      if (Test-TbccServiceWrapperStarting -Title $svc.Title) {
        $report += [pscustomobject]@{
          Id = $svc.Id
          Title = $svc.Title
          KeptPid = 0
          Trimmed = $trimmed.Count
          Restarted = $false
        }
        continue
      }
      Start-TbccStackService -Service $svc -TbccRoot $TbccRoot -UseErrorHubWrapper -Background -Force | Out-Null
      Start-Sleep -Seconds 6
      $after = @(Get-TbccServiceWorkerProcesses -Service $svc)
      $kept = if ($after.Count -gt 0) { [int]$after[0].ProcessId } else { 0 }
      $restarted = $true
    }
    $report += [pscustomobject]@{
      Id = $svc.Id
      Title = $svc.Title
      KeptPid = $kept
      Trimmed = $trimmed.Count
      Restarted = $restarted
    }
  }
  return $report
}

function Ensure-TbccSchedulingWorkersSingleton {
  <# Trim/restart Beat, Celery, Celery-Post only (StackWatch + orchestrator scheduling lane). #>
  param(
    [string]$TbccRoot = "",
    [switch]$FullStack,
    [switch]$TrimOnly
  )
  return @(Ensure-TbccStackWorkersSingleton -TbccRoot $TbccRoot -FullStack:$FullStack -TrimOnly:$TrimOnly `
    -ServiceIds @('beat', 'celery', 'celery_post', 'celery_post_scheduler'))
}

function Remove-TbccStackPairsAlreadyRunning {
  <#
  Trim duplicate workers and skip opening WT tabs when exactly one worker is already up.
  Applies to all stack services (backend, bots, Celery, etc.), not only scheduling workers.
  #>
  param(
    [Parameter(Mandatory = $true)][string[]]$Titles,
    [Parameter(Mandatory = $true)][string[]]$Commands,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack
  )
  if ($Titles.Count -ne $Commands.Count) {
    throw "Remove-TbccStackPairsAlreadyRunning: Titles and Commands count must match."
  }
  $serviceMap = @{}
  foreach ($svc in (Get-TbccStackServices -TbccRoot $TbccRoot -FullStack:$FullStack -MenuCatalog)) {
    $serviceMap[$svc.Title] = $svc
    if ($svc.MenuLabel) { $serviceMap[[string]$svc.MenuLabel] = $svc }
  }
  $outT = New-Object System.Collections.ArrayList
  $outC = New-Object System.Collections.ArrayList
  $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  for ($i = 0; $i -lt $Titles.Count; $i++) {
    $title = $Titles[$i]
    if (-not $serviceMap.ContainsKey($title)) {
      [void]$outT.Add($title)
      [void]$outC.Add($Commands[$i])
      continue
    }
    $svc = $serviceMap[$title]
    $workers = @(Get-TbccServiceWorkerProcesses -Service $svc -AllProcesses $all)
    if ($workers.Count -gt 1) {
      $trimmed = @(Stop-TbccServiceWorkerDuplicates -Service $svc)
      if ($trimmed.Count -gt 0) {
        Write-Host (
          "  [trim] " + $title + " removed " + $trimmed.Count + " duplicate worker(s) before launch"
        ) -ForegroundColor Yellow
      }
      $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
      $workers = @(Get-TbccServiceWorkerProcesses -Service $svc -AllProcesses $all)
    }
    $wrappers = @()
    if (Get-Command Get-TbccServiceTabWrapperProcesses -ErrorAction SilentlyContinue) {
      $wrappers = @(Get-TbccServiceTabWrapperProcesses -ServiceName $title -AllProcesses $all)
    }
    if ($wrappers.Count -gt 1) {
      $sortedW = @($wrappers | Sort-Object { $_.CreationDate })
      foreach ($dup in ($sortedW | Select-Object -Skip 1)) {
        try { Stop-Process -Id $dup.ProcessId -Force -ErrorAction Stop } catch {}
      }
      $wrappers = @($sortedW | Select-Object -First 1)
      Write-Host ("  [trim] " + $title + " closed duplicate WT tab wrapper(s) before launch") -ForegroundColor Yellow
    }
    $alreadyUp = ($workers.Count -ge 1)
    if (-not $alreadyUp -and $svc.Port -gt 0) {
      $alreadyUp = Test-TbccPortListening -Port $svc.Port
    }
    if ($alreadyUp -and $wrappers.Count -ge 1) {
      $pidNote = if ($workers.Count -ge 1) { "pid " + $workers[0].ProcessId } else { "port " + $svc.Port }
      Write-Host ("  [skip] " + $title + " (worker + tab already running, " + $pidNote + ")") -ForegroundColor DarkGray
      continue
    }
    if ($alreadyUp -and $wrappers.Count -eq 0) {
      Write-Host ("  [relaunch] " + $title + " worker without tab - stopping orphan worker") -ForegroundColor Yellow
      $null = Stop-TbccStackService -Service $svc -TbccRoot $TbccRoot
      Start-Sleep -Milliseconds 500
      $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    } elseif (-not $alreadyUp -and $wrappers.Count -ge 1) {
      Write-Host ("  [cleanup] " + $title + " zombie tab (no worker) - closing stale shell") -ForegroundColor Yellow
      if (Get-Command Invoke-TbccCloseServiceTab -ErrorAction SilentlyContinue) {
        $null = Invoke-TbccCloseServiceTab -TbccRoot $TbccRoot -ServiceName $title
      } else {
        $hub = Join-Path $TbccRoot "scripts\tbcc-error-hub.ps1"
        if (Test-Path -LiteralPath $hub) {
          . $hub
          $null = Invoke-TbccCloseServiceTab -TbccRoot $TbccRoot -ServiceName $title
        }
      }
      Start-Sleep -Milliseconds 300
    }
    [void]$outT.Add($title)
    [void]$outC.Add($Commands[$i])
  }
  return @{ Titles = @($outT.ToArray()); Commands = @($outC.ToArray()) }
}

function Remove-TbccSchedulingPairsAlreadyRunning {
  param(
    [Parameter(Mandatory = $true)][string[]]$Titles,
    [Parameter(Mandatory = $true)][string[]]$Commands,
    [Parameter(Mandatory = $true)][string]$TbccRoot
  )
  return Remove-TbccStackPairsAlreadyRunning -Titles $Titles -Commands $Commands -TbccRoot $TbccRoot -FullStack
}

function Get-TbccServiceStatusLabel {
  param(
    $Service,
    $ListeningPorts = $null,
    $AllProcesses = $null
  )
  if (Test-TbccServiceProcessRunning -Service $Service -ListeningPorts $ListeningPorts -AllProcesses $AllProcesses) {
    return "up"
  }
  return "down"
}

function Get-TbccServiceTogglePath {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  Join-Path $TbccRoot ".tbcc-run\service-toggles.json"
}

function Read-TbccServiceToggles {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $path = Get-TbccServiceTogglePath -TbccRoot $TbccRoot
  if (-not (Test-Path -LiteralPath $path)) { return @{} }
  try {
    $raw = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    $map = @{}
    if ($raw -is [System.Collections.IDictionary]) {
      foreach ($k in $raw.Keys) { $map[[string]$k] = [bool]$raw[$k] }
    } elseif ($raw.PSObject.Properties) {
      foreach ($p in $raw.PSObject.Properties) { $map[$p.Name] = [bool]$p.Value }
    }
    return $map
  } catch {
    return @{}
  }
}

function Save-TbccServiceToggles {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)]$Toggles
  )
  $runDir = Join-Path $TbccRoot ".tbcc-run"
  if (-not (Test-Path -LiteralPath $runDir)) {
    New-Item -ItemType Directory -Force -Path $runDir | Out-Null
  }
  $path = Get-TbccServiceTogglePath -TbccRoot $TbccRoot
  ($Toggles | ConvertTo-Json -Compress) | Set-Content -LiteralPath $path -Encoding UTF8
}

function Test-TbccServiceUserEnabled {
  param(
    [Parameter(Mandatory = $true)][string]$ServiceId,
    [Parameter(Mandatory = $true)][string]$TbccRoot
  )
  if ($ServiceId -in $script:TbccMandatoryServiceIds) { return $true }
  $toggles = Read-TbccServiceToggles -TbccRoot $TbccRoot
  if (-not $toggles.ContainsKey($ServiceId)) {
    $profile = Get-TbccStackProfile -TbccRoot $TbccRoot
    $defaultOff = if ($profile -eq 'full') { $script:TbccFullDefaultOffServiceIds } else { $script:TbccLeanDefaultOffServiceIds }
    if ($ServiceId -in $defaultOff) { return $false }
    return $true
  }
  return [bool]$toggles[$ServiceId]
}

function Set-TbccServiceUserEnabled {
  param(
    [Parameter(Mandatory = $true)][string]$ServiceId,
    [Parameter(Mandatory = $true)][bool]$Enabled,
    [Parameter(Mandatory = $true)][string]$TbccRoot
  )
  $toggles = Read-TbccServiceToggles -TbccRoot $TbccRoot
  $toggles[$ServiceId] = $Enabled
  Save-TbccServiceToggles -TbccRoot $TbccRoot -Toggles $toggles
}

function Test-TbccServiceTitleUserEnabled {
  param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$TbccRoot
  )
  if ($Title -eq "TBCC-Errors") { return $true }
  $svc = @(Get-TbccStackServices -TbccRoot $TbccRoot -FullStack -MenuCatalog |
    Where-Object { $_.Title -eq $Title } | Select-Object -First 1)
  if (-not $svc) { return $true }
  return Test-TbccServiceUserEnabled -ServiceId $svc.Id -TbccRoot $TbccRoot
}

function Select-TbccStartedServicePairs {
  <# Filter cold-start title/command pairs using supervisor service toggles. #>
  param(
    [Parameter(Mandatory = $true)][string[]]$Titles,
    [Parameter(Mandatory = $true)][string[]]$Commands,
    [Parameter(Mandatory = $true)][string]$TbccRoot
  )
  if ($Titles.Count -ne $Commands.Count) {
    throw "Select-TbccStartedServicePairs: Titles and Commands count must match."
  }
  $outT = New-Object System.Collections.ArrayList
  $outC = New-Object System.Collections.ArrayList
  for ($i = 0; $i -lt $Titles.Count; $i++) {
    if (Test-TbccServiceTitleUserEnabled -Title $Titles[$i] -TbccRoot $TbccRoot) {
      [void]$outT.Add($Titles[$i])
      [void]$outC.Add($Commands[$i])
    } else {
      Write-Host ("  [skip] " + $Titles[$i] + " (disabled in tray Services menu)") -ForegroundColor DarkGray
    }
  }
  return @{ Titles = @($outT.ToArray()); Commands = @($outC.ToArray()) }
}

function Get-TbccRestartSnapshotPath {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  return Join-Path $TbccRoot ".tbcc-run\restart-service-snapshot.json"
}

function Save-TbccRestartServiceSnapshot {
  <# Record which service tabs were up before tray Restart all (lean/full profile unchanged). #>
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $path = Get-TbccRestartSnapshotPath -TbccRoot $TbccRoot
  $runDir = Split-Path -Parent $path
  if (-not (Test-Path -LiteralPath $runDir)) {
    New-Item -ItemType Directory -Path $runDir -Force | Out-Null
  }
  $cache = Update-TbccServiceStatusCache -TbccRoot $TbccRoot -FullStack -MenuCatalog
  $titles = New-Object System.Collections.ArrayList
  foreach ($entry in $cache.ById.Values) {
    if ($entry.Status -eq "up") {
      [void]$titles.Add([string]$entry.Service.Title)
    }
  }
  foreach ($aux in @("TBCC-Errors", "TBCC-StackWatch", "OpenClaw-Gateway")) {
    if ($titles -contains $aux) { continue }
    if (Test-TbccServiceRecentHubActivity -Title $aux -TbccRoot $TbccRoot) {
      [void]$titles.Add($aux)
    }
  }
  $payload = @{
    savedAtUtc = (Get-Date).ToUniversalTime().ToString("o")
    profile    = (Get-TbccStackProfile -TbccRoot $TbccRoot)
    titles     = @($titles | Select-Object -Unique)
  }
  Set-Content -LiteralPath $path -Value ($payload | ConvertTo-Json -Compress) -Encoding UTF8
  Write-Host ("  [restart] Snapshot {0} running tab(s) ({1} profile)." -f $payload.titles.Count, $payload.profile) -ForegroundColor Gray
  return @($payload.titles)
}

function Clear-TbccRestartServiceSnapshot {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $path = Get-TbccRestartSnapshotPath -TbccRoot $TbccRoot
  if (Test-Path -LiteralPath $path) {
    Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
  }
}

function Read-TbccRestartServiceSnapshot {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $path = Get-TbccRestartSnapshotPath -TbccRoot $TbccRoot
  if (-not (Test-Path -LiteralPath $path)) { return $null }
  try {
    $raw = Get-Content -LiteralPath $path -Raw -Encoding UTF8
    return ($raw | ConvertFrom-Json)
  } catch {
    return $null
  }
}

function Select-TbccRestartSnapshotServicePairs {
  <# Tray Restart all: relaunch only tabs that were running; clear snapshot after read. #>
  param(
    [Parameter(Mandatory = $true)][string[]]$Titles,
    [Parameter(Mandatory = $true)][string[]]$Commands,
    [Parameter(Mandatory = $true)][string]$TbccRoot
  )
  if ($Titles.Count -ne $Commands.Count) {
    throw "Select-TbccRestartSnapshotServicePairs: Titles and Commands count must match."
  }
  $snap = Read-TbccRestartServiceSnapshot -TbccRoot $TbccRoot
  if (-not $snap -or -not $snap.titles) {
    return @{ Titles = $Titles; Commands = $Commands }
  }
  $allowed = @($snap.titles | ForEach-Object { "$_" })
  $outT = New-Object System.Collections.ArrayList
  $outC = New-Object System.Collections.ArrayList
  for ($i = 0; $i -lt $Titles.Count; $i++) {
    if ($allowed -contains $Titles[$i]) {
      [void]$outT.Add($Titles[$i])
      [void]$outC.Add($Commands[$i])
    } else {
      Write-Host ("  [restart-skip] " + $Titles[$i] + " (was not running before restart)") -ForegroundColor DarkGray
    }
  }
  return @{ Titles = @($outT.ToArray()); Commands = @($outC.ToArray()) }
}

function Test-TbccServiceRecentHubActivity {
  param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [int]$TailLines = 48
  )
  $log = Join-Path $TbccRoot ".tbcc-run\error-hub.log"
  if (-not (Test-Path -LiteralPath $log)) { return $false }
  try {
    $lines = @(Get-Content -LiteralPath $log -Tail $TailLines -ErrorAction Stop)
  } catch {
    return $false
  }
  $esc = [regex]::Escape($Title)
  foreach ($line in $lines) {
    if ($line -match $esc) { return $true }
  }
  return $false
}

function Test-TbccServiceRecentHubErrors {
  param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [int]$TailLines = 60
  )
  $log = Join-Path $TbccRoot ".tbcc-run\error-hub.log"
  if (-not (Test-Path -LiteralPath $log)) { return $false }
  try {
    $lines = @(Get-Content -LiteralPath $log -Tail $TailLines -ErrorAction Stop)
  } catch {
    return $false
  }
  $esc = [regex]::Escape($Title)
  foreach ($line in $lines) {
    if ($line -notmatch "ERROR") { continue }
    if ($line -match $esc) { return $true }
  }
  return $false
}

function Get-TbccServiceMenuText {
  param($Service)
  $portLabel = if ($Service.Port -gt 0) { " :" + $Service.Port } else { "" }
  $label = if ($Service.MenuLabel) { [string]$Service.MenuLabel } else { [string]$Service.Title }
  return ($label + $portLabel)
}

function Get-TbccServiceMenuDisplayText {
  param(
    $Service,
    [string]$Status,
    [bool]$UserEnabled
  )
  $base = Get-TbccServiceMenuText -Service $Service
  if (-not $UserEnabled) { return ("[off] " + $base) }
  if ($Status -eq "up") { return ("[on] " + $base) }
  return ("[--] " + $base)
}

function Update-TbccServiceStatusCache {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [switch]$MenuCatalog
  )
  $services = @(Get-TbccStackServices -TbccRoot $TbccRoot -FullStack:$FullStack -MenuCatalog:$MenuCatalog)
  $ports = Get-TbccListeningPortSet
  $procs = @(Get-TbccWin32ProcessListCached)
  $byId = @{}
  $up = 0
  $enabled = 0
  $enabledUp = 0
  foreach ($svc in $services) {
    $label = Get-TbccServiceStatusLabel -Service $svc -ListeningPorts $ports -AllProcesses $procs
    $userOn = Test-TbccServiceUserEnabled -ServiceId $svc.Id -TbccRoot $TbccRoot
    if ($label -eq "up") { $up++ }
    if ($userOn) {
      $enabled++
      if ($label -eq "up") { $enabledUp++ }
    }
    $byId[$svc.Id] = @{
      Service     = $svc
      Status      = $label
      UserEnabled = $userOn
      Text        = (Get-TbccServiceMenuText -Service $svc)
    }
  }
  return @{
    TbccRoot   = $TbccRoot
    FullStack  = [bool]$FullStack
    Services   = $services
    ById       = $byId
    Up         = $up
    Total      = $services.Count
    Enabled    = $enabled
    EnabledUp  = $enabledUp
    UpdatedAt  = Get-Date
  }
}

function Get-TbccStackStatusSummary {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    $Cache = $null
  )
  if ($Cache -and $Cache.ById) {
    return @{
      Services  = $Cache.Services
      Up        = $Cache.Up
      Total     = $Cache.Total
      Enabled   = $Cache.Enabled
      EnabledUp = $Cache.EnabledUp
    }
  }
  $fresh = Update-TbccServiceStatusCache -TbccRoot $TbccRoot -FullStack:$FullStack
  return @{
    Services  = $fresh.Services
    Up        = $fresh.Up
    Total     = $fresh.Total
    Enabled   = $fresh.Enabled
    EnabledUp = $fresh.EnabledUp
  }
}

function Clear-TbccRestartServiceMenu {
  param([Parameter(Mandatory = $true)]$MenuItem)
  if (-not $MenuItem) { return }
  while ($MenuItem.DropDownItems.Count -gt 0) {
    $MenuItem.DropDownItems[0].Dispose()
    [void]$MenuItem.DropDownItems.RemoveAt(0)
  }
}

function Update-TbccSupervisorTrayStatus {
  param(
    [Parameter(Mandatory = $true)]$NotifyIcon,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    $Cache = $null
  )
  $sum = Get-TbccStackStatusSummary -TbccRoot $TbccRoot -FullStack:$FullStack -Cache $Cache
  $profileTag = Get-TbccStackProfileLabel -TbccRoot $TbccRoot
  $NotifyIcon.Text = ("TBCC Supervisor ({0}/{1} running, {2})" -f $sum.EnabledUp, $sum.Enabled, $profileTag)
  if ($NotifyIcon.Text.Length -gt 63) {
    $NotifyIcon.Text = ("TBCC ({0}/{1} run, {2})" -f $sum.EnabledUp, $sum.Enabled, $profileTag)
  }
}

function Invoke-TbccServiceMenuAction {
  param(
    [Parameter(Mandatory = $true)][string]$ServiceId,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [switch]$MenuCatalog,
    [switch]$ForceRestart,
    [scriptblock]$OnNotify
  )
  if (-not $PSBoundParameters.ContainsKey('MenuCatalog')) { $MenuCatalog = $true }
  $svc = @(Get-TbccStackServiceById -ServiceId $ServiceId -TbccRoot $TbccRoot -FullStack:$FullStack -MenuCatalog:$MenuCatalog)
  if (-not $svc) { throw ("Unknown service id: " + $ServiceId) }

  $notify = {
    param([string]$Msg)
    if ($OnNotify) { & $OnNotify $Msg }
  }

  $userOn = Test-TbccServiceUserEnabled -ServiceId $ServiceId -TbccRoot $TbccRoot
  $running = Test-TbccServiceProcessRunning -Service $svc

  if ($ForceRestart) {
    if (-not $userOn) {
      & $notify ($svc.Title + " is disabled - enable it first (click without Ctrl).")
    return
    }
    & $notify ("Restarting " + $svc.Title + "...")
    $null = Restart-TbccStackService -ServiceId $ServiceId -TbccRoot $TbccRoot -FullStack -UseErrorHubWrapper
    & $notify ($svc.Title + " restarted.")
    return
  }

  if ($userOn) {
    Set-TbccServiceUserEnabled -ServiceId $ServiceId -Enabled $false -TbccRoot $TbccRoot
    if ($running) {
      $busy = Test-TbccServiceRecentHubActivity -Title $svc.Title -TbccRoot $TbccRoot
      $errLoop = Test-TbccServiceRecentHubErrors -Title $svc.Title -TbccRoot $TbccRoot
      if ($busy -and $errLoop) {
        & $notify ($svc.Title + ": stopping (recent errors in hub - may still be busy).")
      } elseif ($busy) {
        & $notify ($svc.Title + ": stopping gracefully (may finish in-flight work).")
      } else {
        & $notify ("Stopping " + $svc.Title + "...")
      }
      $null = Stop-TbccStackService -Service $svc -TbccRoot $TbccRoot
      Start-Sleep -Milliseconds 500
      & $notify ($svc.Title + " disabled.")
    } else {
      & $notify ($svc.Title + " disabled (was not running).")
    }
    return
  }

  Set-TbccServiceUserEnabled -ServiceId $ServiceId -Enabled $true -TbccRoot $TbccRoot
  & $notify ("Starting " + $svc.Title + "...")
  Start-TbccStackService -Service $svc -TbccRoot $TbccRoot -UseErrorHubWrapper
  & $notify ($svc.Title + " enabled.")
}

function Initialize-TbccServiceToggleMenu {
  <#
  Services submenu (Extensity-style): white = enabled, gray = disabled. Click toggles; Ctrl+click restarts.
  Returns hashtable serviceId -> ToolStripMenuItem for live UI updates.
  MenuCatalog lists every optional process (lean stack still controls cold-start only).
  #>
  param(
    [Parameter(Mandatory = $true)]$MenuItem,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [switch]$MenuCatalog,
    [scriptblock]$OnNotify,
    [scriptblock]$OnChanged
  )
  if (-not $PSBoundParameters.ContainsKey('MenuCatalog')) { $MenuCatalog = $true }
  Clear-TbccRestartServiceMenu -MenuItem $MenuItem
  $map = @{}
  foreach ($svc in (Get-TbccStackServices -TbccRoot $TbccRoot -FullStack:$FullStack -MenuCatalog:$MenuCatalog)) {
    $item = New-Object System.Windows.Forms.ToolStripMenuItem
    $item.Text = Get-TbccServiceMenuText -Service $svc
    $item.Tag = @{ Id = $svc.Id; Title = $svc.Title; TbccUserEnabled = $true }
    $sid = $svc.Id
    [void]$item.Add_Click({
      param($sender, $e)
      $ctrl = ([System.Windows.Forms.Control]::ModifierKeys -band [System.Windows.Forms.Keys]::Control) -ne 0
      try {
        Invoke-TbccServiceMenuAction -ServiceId $sid -TbccRoot $TbccRoot -FullStack:$FullStack -MenuCatalog `
          -ForceRestart:$ctrl -OnNotify $OnNotify
        if ($OnChanged) { & $OnChanged }
      } catch {
        if ($OnNotify) { & $OnNotify ("Service action failed: " + $_.Exception.Message) }
      }
    }.GetNewClosure())
    [void]$MenuItem.DropDownItems.Add($item)
    $map[$svc.Id] = $item
  }
  $hint = New-Object System.Windows.Forms.ToolStripMenuItem
  $hint.Text = "[on] running  [--] stopped  [off] disabled  |  click toggle  Ctrl restart"
  $hint.Tag = @{ TbccMenuHint = $true; TbccUserEnabled = $false; TbccRunning = $false }
  $hint.Enabled = $false
  [void]$MenuItem.DropDownItems.Add((New-Object System.Windows.Forms.ToolStripSeparator))
  [void]$MenuItem.DropDownItems.Add($hint)
  return $map
}

function Apply-TbccServiceMenuItemsUi {
  param(
    [Parameter(Mandatory = $true)]$MenuItemsById,
    $Cache
  )
  if (-not $Cache -or -not $Cache.ById) { return }
  foreach ($id in $MenuItemsById.Keys) {
    $row = $Cache.ById[$id]
    if (-not $row) { continue }
    $item = $MenuItemsById[$id]
    if ($item.Tag -and $item.Tag.TbccMenuHint) { continue }
    $running = ($row.Status -eq "up")
    $item.Text = Get-TbccServiceMenuDisplayText -Service $row.Service -Status $row.Status -UserEnabled:([bool]$row.UserEnabled)
    if (-not $item.Tag) { $item.Tag = @{} }
    $item.Tag.TbccUserEnabled = [bool]$row.UserEnabled
    $item.Tag.TbccRunning = $running
    $item.Enabled = $true
    if ($row.UserEnabled) {
      if ($running) {
        $item.ToolTipText = "Running - click to stop/disable | Ctrl+click restart"
      } else {
        $item.ToolTipText = "Stopped (enabled) - click to disable | Ctrl+click start"
      }
    } else {
      $item.ToolTipText = "Disabled - click to enable and start"
    }
  }
}

function Initialize-TbccRestartServiceMenu {
  param(
    [Parameter(Mandatory = $true)]$MenuItem,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [scriptblock]$OnRestarted,
    [scriptblock]$OnChanged
  )
  return Initialize-TbccServiceToggleMenu -MenuItem $MenuItem -TbccRoot $TbccRoot -FullStack:$FullStack `
    -OnNotify $OnRestarted -OnChanged $OnChanged
}

function Apply-TbccRestartServiceMenuLabels {
  param(
    [Parameter(Mandatory = $true)]$MenuItemsById,
    $Cache
  )
  Apply-TbccServiceMenuItemsUi -MenuItemsById $MenuItemsById -Cache $Cache
}

function Stop-TbccStackService {
  param(
    [Parameter(Mandatory = $true)]$Service,
    [string]$TbccRoot,
    [switch]$GracefulTabClose
  )
  $exclude = @()
  if ($TbccRoot) {
    $exclude = @(Get-TbccStopExcludeProcessIds)
  }
  $killed = @()
  if ($Service.Port -gt 0) {
    $killed += @(Stop-TbccListenersOnPort -Port $Service.Port -ExcludeProcessIds $exclude)
  }
  if ($Service.CommandMatch) {
    $null = Stop-TbccServiceWorkerDuplicates -Service $Service -ExcludeProcessIds $exclude
    $killed += @(Stop-TbccProcessesByCommandMatch -Pattern $Service.CommandMatch -ExcludeProcessIds $exclude)
    $killed += @(Stop-TbccProcessesByCommandMatch -Pattern ('py\.exe.*' + $Service.CommandMatch) -ExcludeProcessIds $exclude)
  }
  if ($TbccRoot) {
    $killed += @(Stop-TbccProcessesByServiceTitle -Title $Service.Title -TbccRoot $TbccRoot -GracefulTabClose:$GracefulTabClose)
  }
  return @($killed | Select-Object -Unique)
}

function Wait-TbccServiceTabClosed {
  param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [int]$MaxWaitSeconds = 12
  )
  $deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
  while ((Get-Date) -lt $deadline) {
    $wrappers = @()
    if (Get-Command Get-TbccServiceTabWrapperProcesses -ErrorAction SilentlyContinue) {
      $wrappers = @(Get-TbccServiceTabWrapperProcesses -ServiceName $Title)
    }
    $sessionPath = $null
    $shellPath = $null
    if (Get-Command Get-TbccServiceTabSessionPath -ErrorAction SilentlyContinue) {
      $sessionPath = Get-TbccServiceTabSessionPath -TbccRoot $TbccRoot -ServiceName $Title
    }
    if (Get-Command Get-TbccServiceTabShellPidPath -ErrorAction SilentlyContinue) {
      $shellPath = Get-TbccServiceTabShellPidPath -TbccRoot $TbccRoot -ServiceName $Title
    }
    $sessionGone = (-not $sessionPath) -or (-not (Test-Path -LiteralPath $sessionPath))
    $shellGone = (-not $shellPath) -or (-not (Test-Path -LiteralPath $shellPath))
    if ($wrappers.Count -eq 0 -and $sessionGone -and $shellGone) { return $true }
    Start-Sleep -Milliseconds 250
  }
  return $false
}

function Get-TbccWtHostPid {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $runDir = Join-Path $TbccRoot ".tbcc-run"
  foreach ($name in @('windows-terminal-host.pid', 'wt-tab-host.pid')) {
    $f = Join-Path $runDir $name
    if (-not (Test-Path -LiteralPath $f)) { continue }
    try {
      $pidVal = [int]((Get-Content -LiteralPath $f -Raw -ErrorAction Stop).Trim())
      if ($pidVal -le 4) { continue }
      $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pidVal" -ErrorAction SilentlyContinue
      if (-not $proc) { continue }
      $pn = [string]$proc.Name
      if ($pn -ieq 'WindowsTerminal.exe') { return $pidVal }
    } catch {}
  }
  $hosts = @(Get-TbccWindowsTerminalHostPids -TbccRoot $TbccRoot)
  if ($hosts.Count -gt 0) { return [int]$hosts[0] }
  return $null
}

function Get-TbccWtExePath {
  foreach ($p in @(
    (Join-Path ${env:ProgramFiles} "Windows Terminal\wt.exe"),
    (Join-Path $env:LOCALAPPDATA "Microsoft\Windows Terminal\wt.exe")
  )) {
    if (Test-Path -LiteralPath $p) { return $p }
  }
  try {
    $pkg = Get-AppxPackage -Name Microsoft.WindowsTerminal -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pkg -and $pkg.InstallLocation) {
      $appxWt = Join-Path $pkg.InstallLocation "wt.exe"
      if (Test-Path -LiteralPath $appxWt) { return $appxWt }
    }
  } catch {}
  try {
    $c = Get-Command "wt.exe" -ErrorAction Stop
    return $c.Source
  } catch {}
  return $null
}

function Start-TbccWtTab {
  <#
  Open one service tab in an existing TBCC Windows Terminal window when possible.
  Returns $true if wt.exe was used, $false if caller should fall back to cmd.exe.
  #>
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$Command,
    [int]$WtHostPid = 0,
    [switch]$NewWindow,
    [switch]$Minimized
  )
  $wtExe = Get-TbccWtExePath
  if (-not $wtExe) { return $false }

  $prefs = Get-TbccTerminalWindowPrefs -TbccRoot $TbccRoot
  $hubScript = Join-Path $TbccRoot "scripts\tbcc-error-hub.ps1"
  if (Test-Path -LiteralPath $hubScript) { . $hubScript }

  if ($WtHostPid -le 0 -and -not $NewWindow) {
    $WtHostPid = Get-TbccWtHostPid -TbccRoot $TbccRoot
  }

  $al = New-Object System.Collections.ArrayList
  if ($NewWindow -or -not $WtHostPid) {
    [void]$al.Add('-w')
    [void]$al.Add('-1')
    if ($prefs.WtWidth -gt 0 -and $prefs.WtHeight -gt 0) {
      [void]$al.Add('--size')
      [void]$al.Add(("{0},{1}" -f $prefs.WtWidth, $prefs.WtHeight))
    }
  } else {
    [void]$al.Add('-w')
    [void]$al.Add("$WtHostPid")
  }

  if (Get-Command Add-TbccWtTabShellInvocation -ErrorAction SilentlyContinue) {
    Add-TbccWtTabShellInvocation -ArgumentList $al -TbccRoot $TbccRoot -Title $Title -Command $Command -Cols $prefs.Cols -Lines $prefs.Lines
  } else {
    $null = Register-TbccSelfClosingServiceTab -TbccRoot $TbccRoot -ServiceName $Title -Command $Command
    $runner = Join-Path $TbccRoot "scripts\run-tbcc-service.ps1"
    Start-Process -FilePath "powershell.exe" -ArgumentList @(
      '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
      '-File', $runner, '-TbccRoot', $TbccRoot, '-ServiceName', $Title
    ) -WindowStyle Normal
    return $true
  }

  $openingNewWindow = ($NewWindow -or -not $WtHostPid)
  if (-not $openingNewWindow -and (Get-Command Invoke-TbccWtCommandSilent -ErrorAction SilentlyContinue)) {
    $null = Invoke-TbccWtCommandSilent -WtExe $wtExe -WtArgs @($al.ToArray())
    return $true
  }
  $winStyle = if ($openingNewWindow -and $Minimized) { 'Minimized' } else { 'Normal' }
  $proc = Start-Process -FilePath $wtExe -ArgumentList @($al.ToArray()) -WindowStyle $winStyle -PassThru
  if ($proc -and $openingNewWindow) {
    Register-TbccWtTabHostFromLauncher -TbccRoot $TbccRoot -LauncherPid $proc.Id
  }
  return $true
}

function Get-TbccCurrentWindowsTerminalPid {
  try {
    $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    if ($all.Count -eq 0) { return $null }
    $byId = @{}
    foreach ($p in $all) { $byId[[int]$p.ProcessId] = $p }
    $cur = [int]$PID
    $seen = @{}
    while ($cur -gt 4 -and -not $seen.ContainsKey($cur)) {
      $seen[$cur] = $true
      if (-not $byId.ContainsKey($cur)) { break }
      $proc = $byId[$cur]
      $name = [string]$proc.Name
      if ($name -ieq 'WindowsTerminal.exe') { return $cur }
      $cur = [int]$proc.ParentProcessId
    }
  } catch {}
  return $null
}

function Get-TbccOrchestratorProcessTreeIds {
  param([int[]]$Extra = @())
  $ids = New-Object 'System.Collections.Generic.HashSet[int]'
  foreach ($e in $Extra) {
    if ($e -gt 4) { [void]$ids.Add([int]$e) }
  }
  try {
    $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    foreach ($pr in $all) {
      $cmd = [string]$pr.CommandLine
      if ($cmd -match 'run-tbcc-orchestrator\.ps1|tbcc-orchestrate\.ps1') {
        foreach ($tp in (Get-TbccProcessTreePids -RootPid $pr.ProcessId -AllProcesses $all)) {
          [void]$ids.Add([int]$tp)
        }
      }
    }
    $wt = Get-TbccCurrentWindowsTerminalPid
    if ($wt) { [void]$ids.Add([int]$wt) }
  } catch {}
  return @($ids)
}

function Get-TbccOrchestratorResultPath {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  Join-Path $TbccRoot ".tbcc-run\orchestrator-result.json"
}

function Write-TbccOrchestratorResult {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][ValidateSet("Stop", "Restart", "ColdStart")][string]$Action,
    [Parameter(Mandatory = $true)][bool]$Success,
    [Parameter(Mandatory = $true)][string]$Message
  )
  $runDir = Join-Path $TbccRoot ".tbcc-run"
  if (-not (Test-Path -LiteralPath $runDir)) {
    New-Item -ItemType Directory -Force -Path $runDir | Out-Null
  }
  $msg = [string]$Message
  if ($msg.Length -gt 500) { $msg = $msg.Substring(0, 497) + "..." }
  $obj = @{
    action     = $Action
    success    = $Success
    message    = $msg
    finishedAt = (Get-Date).ToString("o")
  }
  try {
    ($obj | ConvertTo-Json -Compress) | Set-Content -LiteralPath (Get-TbccOrchestratorResultPath -TbccRoot $TbccRoot) -Encoding UTF8
  } catch {}
}

function Read-TbccOrchestratorResult {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $path = Get-TbccOrchestratorResultPath -TbccRoot $TbccRoot
  if (-not (Test-Path -LiteralPath $path)) { return $null }
  try {
    return (Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json)
  } catch {
    return $null
  }
}

function Test-TbccOrchestratorRunning {
  try {
    foreach ($pr in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) {
      $cmd = [string]$pr.CommandLine
      if ($cmd -match 'run-tbcc-orchestrator\.ps1|tbcc-orchestrate\.ps1') { return $true }
    }
  } catch {}
  return $false
}

function Get-TbccStackResidualSummary {
  <# Stack services still running after a stop attempt (not WT window presence). #>
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack
  )
  $issues = New-Object System.Collections.ArrayList
  $cache = Update-TbccServiceStatusCache -TbccRoot $TbccRoot -FullStack:$FullStack
  foreach ($id in @($cache.ById.Keys)) {
    $entry = $cache.ById[$id]
    if ($entry.Status -eq "up") {
      [void]$issues.Add([string]$entry.Text)
    }
  }
  return @($issues.ToArray())
}

function Get-TbccEnabledServicesDownSummary {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [string[]]$OnlyTitles = @()
  )
  $down = New-Object System.Collections.ArrayList
  $cache = Update-TbccServiceStatusCache -TbccRoot $TbccRoot -FullStack:$FullStack
  $scope = @($OnlyTitles | Where-Object { $_ })
  $scoped = ($scope.Count -gt 0)
  foreach ($id in @($cache.ById.Keys)) {
    $entry = $cache.ById[$id]
    if ($scoped -and ($scope -notcontains $entry.Service.Title)) { continue }
    if ($entry.UserEnabled -and $entry.Status -ne "up") {
      [void]$down.Add([string]$entry.Text)
    }
  }
  return @($down.ToArray())
}

function Build-TbccOrchestratorStopMessage {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][bool]$FullyStopped
  )
  if ($FullyStopped) {
    return "All TBCC services stopped. Safe to cold-start again."
  }
  $left = @(Get-TbccStackResidualSummary -TbccRoot $TbccRoot -FullStack)
  if ($left.Count -eq 0) {
    return "Stop finished - no stack services detected running."
  }
  $list = ($left | Select-Object -First 4) -join ", "
  if ($left.Count -gt 4) { $list += (" (+{0} more)" -f ($left.Count - 4)) }
  return ("Still running: " + $list + ". Tray: Stop again or Cleanup orphan API workers.")
}

function Build-TbccOrchestratorStartMessage {
  param(
    [Parameter(Mandatory = $true)][ValidateSet("Restart", "ColdStart")][string]$Action,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [bool]$PriorStackStopped = $true,
    [string]$StartFailure = "",
    [string[]]$ExpectedTitles = @()
  )
  if ($StartFailure) {
    $verb = if ($Action -eq "ColdStart") { "Cold start" } else { "Restart" }
    return ($verb + " failed - " + $StartFailure)
  }
  $cache = Update-TbccServiceStatusCache -TbccRoot $TbccRoot -FullStack
  $down = @(Get-TbccEnabledServicesDownSummary -TbccRoot $TbccRoot -FullStack -OnlyTitles $ExpectedTitles)
  $verb = if ($Action -eq "ColdStart") { "Cold start" } else { "Restart" }
  if ($down.Count -eq 0) {
    $msg = ("{0} complete - all enabled services are up ({1}/{2})." -f $verb, $cache.EnabledUp, $cache.Enabled)
    if (-not $PriorStackStopped) {
      $msg += " Note: prior stack may not have fully stopped before launch."
    }
    return $msg
  }
  $list = ($down | Select-Object -First 4) -join ", "
  if ($down.Count -gt 4) { $list += (" (+{0} more)" -f ($down.Count - 4)) }
  $msg = ("{0} finished - not up: {1} ({2}/{3} enabled services running)." -f $verb, $list, $cache.EnabledUp, $cache.Enabled)
  if (-not $PriorStackStopped) {
    $msg += " Prior stack may not have fully stopped."
  }
  $msg += " Check TBCC-Orchestrator tab or error-hub.log."
  return $msg
}

function Refresh-TbccWtHostPid {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [int]$PreferredPid = 0
  )
  $pidVal = if ($PreferredPid -gt 0) { $PreferredPid } else { Get-TbccCurrentWindowsTerminalPid }
  if (-not $pidVal) { $pidVal = Get-TbccWtHostPid -TbccRoot $TbccRoot }
  if (-not $pidVal) { return }
  $runDir = Join-Path $TbccRoot ".tbcc-run"
  if (-not (Test-Path -LiteralPath $runDir)) {
    New-Item -ItemType Directory -Path $runDir -Force | Out-Null
  }
  Set-Content -LiteralPath (Join-Path $runDir "windows-terminal-host.pid") -Value $pidVal -Encoding ascii -NoNewline
}

function Wait-TbccStackServicesStopped {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [int]$MaxWaitSeconds = 60
  )
  $services = Get-TbccStackServices -TbccRoot $TbccRoot -FullStack:$FullStack
  $ports = @($services | Where-Object { $_.Port -gt 0 } | ForEach-Object { $_.Port } | Select-Object -Unique)
  $deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
  while ((Get-Date) -lt $deadline) {
    $busy = $false
    foreach ($p in $ports) {
      if (Test-TbccPortListening -Port $p) { $busy = $true; break }
    }
    if (-not $busy) {
      foreach ($svc in $services) {
        if (Test-TbccServiceProcessRunning -Service $svc) { $busy = $true; break }
      }
    }
    if (-not $busy) { return $true }
    Start-Sleep -Milliseconds 400
  }
  return $false
}

function Stop-TbccStackGracefully {
  <#
  Stop TBCC services one-by-one so each tab closes as its worker exits; keep Windows Terminal host + orchestrator tab.
  #>
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [int[]]$ExcludeProcessIds = @(),
    [switch]$Wait,
    [int]$MaxWaitSeconds = 60
  )
  $exclude = @(Get-TbccStopExcludeProcessIds -Extra $ExcludeProcessIds)
  $exclude += @(Get-TbccOrchestratorProcessTreeIds -Extra $ExcludeProcessIds)
  $exclude = @($exclude | Select-Object -Unique)

  $hubScript = Join-Path $TbccRoot "scripts\tbcc-error-hub.ps1"
  if (Test-Path -LiteralPath $hubScript) { . $hubScript }
  Refresh-TbccWtHostPid -TbccRoot $TbccRoot

  $services = Get-TbccStackServices -TbccRoot $TbccRoot -FullStack:$FullStack
  $ordered = @($services | Sort-Object {
    if ($_.Id -eq 'backend') { 1000 }
    elseif ($_.Port -gt 0) { 500 - $_.Port }
    else { 100 }
  })

  foreach ($svc in $ordered) {
    Write-Host ("  stopping " + $svc.Title + " (close tab)...") -ForegroundColor Yellow
    $null = Stop-TbccStackService -Service $svc -TbccRoot $TbccRoot -GracefulTabClose
    $tabClosed = Wait-TbccServiceTabClosed -Title $svc.Title -TbccRoot $TbccRoot -MaxWaitSeconds 12
    if (-not $tabClosed) {
      Write-Host ("    tab still open for " + $svc.Title + " - forcing close") -ForegroundColor DarkYellow
      if (Get-Command Invoke-TbccCloseServiceTab -ErrorAction SilentlyContinue) {
        $null = Invoke-TbccCloseServiceTab -TbccRoot $TbccRoot -ServiceName $svc.Title
      }
    }
  }

  if (Get-Command Invoke-TbccSweepStaleServiceTabShells -ErrorAction SilentlyContinue) {
    Invoke-TbccSweepStaleServiceTabShells -TbccRoot $TbccRoot
  }

  $null = Stop-TbccProcessesByCommandMatch -Pattern 'run-tbcc-service\.ps1' -ExcludeProcessIds $exclude
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'show-tbcc-error-hub' -ExcludeProcessIds $exclude
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'run-tbcc-stackwatch\.ps1|show-tbcc-processes\.ps1' -ExcludeProcessIds $exclude
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'title\s+"(TBCC-|AOF-Forum|OpenClaw-Gateway)' -ExcludeProcessIds $exclude

  foreach ($svc in ($services | Where-Object { $_.Port -gt 0 })) {
    $null = Stop-TbccListenersOnPort -Port $svc.Port -ExcludeProcessIds $exclude
  }

  $stray = @(Stop-TbccStrayStackProcesses -TbccRoot $TbccRoot -ExcludeProcessIds $exclude)
  if ($stray.Count -gt 0) {
    Write-Host ("  killed {0} stray TBCC worker(s)" -f $stray.Count) -ForegroundColor DarkYellow
  }

  # Hub / audit tabs are not stack services but keep ports and confuse supervisor counts.
  foreach ($hubTitle in @('TBCC-Errors', 'TBCC-StackWatch')) {
    $null = Stop-TbccProcessesByServiceTitle -Title $hubTitle -TbccRoot $TbccRoot
    if (Get-Command Invoke-TbccCloseServiceTab -ErrorAction SilentlyContinue) {
      $null = Invoke-TbccCloseServiceTab -TbccRoot $TbccRoot -ServiceName $hubTitle
    }
  }

  # Second pass — force anything still listening / matching stack patterns.
  Start-Sleep -Milliseconds 400
  foreach ($svc in $services) {
    if (Test-TbccServiceProcessRunning -Service $svc) {
      Write-Host ("  force stop " + $svc.Title + "...") -ForegroundColor DarkYellow
      $null = Stop-TbccStackService -Service $svc -TbccRoot $TbccRoot
    }
  }
  $stray2 = @(Stop-TbccStrayStackProcesses -TbccRoot $TbccRoot -ExcludeProcessIds $exclude)
  if ($stray2.Count -gt 0) {
    Write-Host ("  killed {0} lingering worker(s) on pass 2" -f $stray2.Count) -ForegroundColor DarkYellow
  }

  $ocKilled = @(Stop-TbccOpenClawGatewaySurfaces -TbccRoot $TbccRoot -ExcludeProcessIds $exclude)
  if ($ocKilled.Count -gt 0) {
    Write-Host ("  stopped OpenClaw gateway ({0} process(es))" -f $ocKilled.Count) -ForegroundColor DarkGray
  }

  $cleanupOrphans = Join-Path $TbccRoot "scripts\tbcc-cleanup-orphans.ps1"
  if (Test-Path -LiteralPath $cleanupOrphans) {
    try {
      Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $cleanupOrphans
      ) -WindowStyle Hidden -Wait | Out-Null
    } catch {}
  }

  if (Get-Command Invoke-TbccProcessAudit -ErrorAction SilentlyContinue) {
    $null = Invoke-TbccProcessAudit -TbccRoot $TbccRoot -Full -LogIssues -Quiet -Phase "post-stop"
  } else {
    $auditMod = Join-Path $TbccRoot "scripts\tbcc-process-audit.ps1"
    if (Test-Path -LiteralPath $auditMod) {
      . $auditMod
      $null = Invoke-TbccProcessAudit -TbccRoot $TbccRoot -Full -LogIssues -Quiet -Phase "post-stop"
    }
  }

  if ($Wait) {
    return (Wait-TbccStackServicesStopped -TbccRoot $TbccRoot -FullStack:$FullStack -MaxWaitSeconds $MaxWaitSeconds)
  }
  return $true
}

function Get-TbccOrchestratorWrapperCmd {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string]$Action,
    [switch]$NoOpen
  )
  $runner = Join-Path $TbccRoot "scripts\run-tbcc-orchestrator.ps1"
  $runQ = '"' + $runner + '"'
  $rootQ = '"' + $TbccRoot + '"'
  $cmd = 'powershell -NoProfile -ExecutionPolicy Bypass -File ' + $runQ + ' -TbccRoot ' + $rootQ + ' -Action ' + $Action
  if ($NoOpen) { $cmd += ' -NoOpen' }
  return $cmd
}

function Invoke-TbccOrchestrateInWt {
  <#
  Launch TBCC-Orchestrator tab in the existing TBCC Windows Terminal window (or one new window if none).
  No separate PowerShell launcher window is opened.
  #>
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][ValidateSet("Stop", "Restart", "ColdStart")][string]$Action,
    [switch]$NoOpen
  )

  $hubScript = Join-Path $TbccRoot "scripts\tbcc-error-hub.ps1"
  if (Test-Path -LiteralPath $hubScript) { . $hubScript }

  $hostPid = Get-TbccWtHostPid -TbccRoot $TbccRoot
  if (-not $hostPid) {
    $hostPid = Get-TbccCurrentWindowsTerminalPid
  }

  # Stop with no TBCC window yet: run inline (no flash of a throwaway WT window).
  if ($Action -eq "Stop" -and -not $hostPid) {
    if (-not (Test-Path -LiteralPath (Join-Path $TbccRoot "scripts\tbcc-service-control.ps1"))) {
      throw "Missing tbcc-service-control.ps1"
    }
    $gone = Stop-TbccStackGracefully -TbccRoot $TbccRoot -FullStack -Wait -MaxWaitSeconds 60
    $msg = Build-TbccOrchestratorStopMessage -TbccRoot $TbccRoot -FullyStopped:$gone
    Write-TbccOrchestratorResult -TbccRoot $TbccRoot -Action Stop -Success:$gone -Message $msg
    return
  }

  $cmd = Get-TbccOrchestratorWrapperCmd -TbccRoot $TbccRoot -Action $Action -NoOpen:$NoOpen
  if ($Action -in @('ColdStart', 'Restart') -and (Get-Command Clear-TbccSchedulingWorkersBeforeLaunch -ErrorAction SilentlyContinue)) {
    $null = Clear-TbccSchedulingWorkersBeforeLaunch -SettleMs 500
  }
  try {
    if ($hostPid) {
      $ok = Start-TbccWtTab -TbccRoot $TbccRoot -Title "TBCC-Orchestrator" -Command $cmd -WtHostPid $hostPid
    } else {
      $ok = Start-TbccWtTab -TbccRoot $TbccRoot -Title "TBCC-Orchestrator" -Command $cmd -NewWindow -Minimized
    }
    if (-not $ok) {
      throw "Could not open TBCC-Orchestrator tab (wt.exe missing or failed)."
    }
  } catch {
    $msg = "Invoke-TbccOrchestrateInWt failed: " + $_.Exception.Message
    if (Get-Command Write-TbccErrorHubEntry -ErrorAction SilentlyContinue) {
      Write-TbccErrorHubEntry -TbccRoot $TbccRoot -ServiceName "TBCC-Orchestrator" -Level "ERROR" -Message $msg
    }
    throw
  }
}

function Start-TbccWtTabs {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string[]]$Titles,
    [Parameter(Mandatory = $true)][string[]]$Commands,
    [int]$Cols = 84,
    [int]$Lines = 24,
    [int]$WtWidth = 820,
    [int]$WtHeight = 460,
    [int]$WtHostPid = 0
  )
  $wtExe = Get-TbccWtExePath
  if (-not $wtExe) {
    Write-Host '  Windows Terminal (wt.exe) not found - opening separate cmd windows instead.' -ForegroundColor DarkYellow
    return $false
  }
  if ($Titles.Length -ne $Commands.Length) {
    throw "Start-TbccWtTabs: Titles and Commands count must match."
  }

  $reuseWindow = ($WtHostPid -gt 0)
  if (-not $reuseWindow) {
    $WtHostPid = Get-TbccWtHostPid -TbccRoot $TbccRoot
    $reuseWindow = ($WtHostPid -gt 0)
  }

  $hubScript = Join-Path $TbccRoot "scripts\tbcc-error-hub.ps1"
  if (Test-Path -LiteralPath $hubScript) { . $hubScript }

  $al = New-Object System.Collections.ArrayList
  for ($i = 0; $i -lt $Titles.Length; $i++) {
    if ($i -gt 0) { [void]$al.Add(';') }
    if ($i -eq 0) {
      [void]$al.Add('-w')
      if ($reuseWindow) {
        [void]$al.Add("$WtHostPid")
      } else {
        [void]$al.Add('-1')
        if ($WtWidth -gt 0 -and $WtHeight -gt 0) {
          [void]$al.Add('--size')
          [void]$al.Add(("{0},{1}" -f $WtWidth, $WtHeight))
        }
      }
    }
    if (Get-Command Add-TbccWtTabShellInvocation -ErrorAction SilentlyContinue) {
      Add-TbccWtTabShellInvocation -ArgumentList $al -TbccRoot $TbccRoot -Title $Titles[$i] -Command $Commands[$i] -Cols $Cols -Lines $Lines
    } else {
      $wrap = Register-TbccSelfClosingServiceTab -TbccRoot $TbccRoot -ServiceName $Titles[$i] -Command $Commands[$i]
      $runner = Join-Path $TbccRoot "scripts\run-tbcc-service.ps1"
      [void]$al.Add('new-tab')
      [void]$al.Add('--title')
      [void]$al.Add($Titles[$i])
      [void]$al.Add('powershell')
      [void]$al.Add('-NoProfile')
      [void]$al.Add('-NonInteractive')
      [void]$al.Add('-ExecutionPolicy')
      [void]$al.Add('Bypass')
      [void]$al.Add('-File')
      [void]$al.Add($runner)
      [void]$al.Add('-TbccRoot')
      [void]$al.Add($TbccRoot)
      [void]$al.Add('-ServiceName')
      [void]$al.Add($Titles[$i])
    }
  }

  if ($reuseWindow -and (Get-Command Invoke-TbccWtCommandSilent -ErrorAction SilentlyContinue)) {
    $null = Invoke-TbccWtCommandSilent -WtExe $wtExe -WtArgs @($al.ToArray()) -TimeoutMs 120000
    Refresh-TbccWtHostPid -TbccRoot $TbccRoot -PreferredPid $WtHostPid
    return $true
  }

  $winStyle = if (Test-TbccWtLaunchMinimized -TbccRoot $TbccRoot) { 'Minimized' } else { 'Normal' }
  $proc = Start-Process -FilePath $wtExe -ArgumentList @($al.ToArray()) -WindowStyle $winStyle -PassThru
  if ($proc -and -not $reuseWindow) {
    Register-TbccWtTabHostFromLauncher -TbccRoot $TbccRoot -LauncherPid $proc.Id
  } elseif ($reuseWindow) {
    Refresh-TbccWtHostPid -TbccRoot $TbccRoot -PreferredPid $WtHostPid
  }
  return $true
}

function Invoke-TbccPrepareWtTabLaunch {
  <# Clear stale tab registry and zombie shells before opening a fresh WT tab batch. #>
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $hub = Join-Path $TbccRoot "scripts\tbcc-error-hub.ps1"
  if (-not (Test-Path -LiteralPath $hub)) { return }
  . $hub
  if (Get-Command Invoke-TbccSweepStaleServiceTabShells -ErrorAction SilentlyContinue) {
    Invoke-TbccSweepStaleServiceTabShells -TbccRoot $TbccRoot
  }
  $tabDir = Get-TbccServiceTabDir -TbccRoot $TbccRoot
  if (-not (Test-Path -LiteralPath $tabDir)) { return }
  $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  foreach ($shellFile in @(Get-ChildItem -LiteralPath $tabDir -Filter '*.shell.pid' -ErrorAction SilentlyContinue)) {
    $svc = $shellFile.BaseName
    try {
      $shellPid = [int]((Get-Content -LiteralPath $shellFile.FullName -Raw -ErrorAction Stop).Trim())
      $live = $all | Where-Object { $_.ProcessId -eq $shellPid } | Select-Object -First 1
      if (-not $live) {
        Clear-TbccServiceTabSession -TbccRoot $TbccRoot -ServiceName $svc
        Clear-TbccServiceTabShell -TbccRoot $TbccRoot -ServiceName $svc
      }
    } catch {
      Remove-Item -LiteralPath $shellFile.FullName -Force -ErrorAction SilentlyContinue
    }
  }
}

function Start-TbccStackService {
  param(
    [Parameter(Mandatory = $true)]$Service,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$UseErrorHubWrapper,
    [switch]$Force,
    [switch]$Background
  )
  $cmd = $Service.Command
  if (-not $cmd) { throw ("No command for service " + $Service.Title) }

  $hubPath = Join-Path $TbccRoot "scripts\tbcc-error-hub.ps1"
  if (-not $PSBoundParameters.ContainsKey('UseErrorHubWrapper') -and (Test-Path -LiteralPath $hubPath)) {
    $UseErrorHubWrapper = $true
  }

  $null = Stop-TbccServiceWorkerDuplicates -Service $Service

  $remaining = @(Get-TbccServiceWorkerProcesses -Service $Service)
  if ($remaining.Count -gt 1) {
    Write-Warning (
      "{0}: {1} workers still running after dedupe - retrying kill (PIDs {2})" -f
      $Service.Title, $remaining.Count, (($remaining | ForEach-Object { $_.ProcessId }) -join ", ")
    )
    $null = Stop-TbccServiceWorkerDuplicates -Service $Service
    $remaining = @(Get-TbccServiceWorkerProcesses -Service $Service)
  }

  if ($Force -and $remaining.Count -ge 1) {
    $exclude = @(Get-TbccStopExcludeProcessIds)
    $null = Stop-TbccProcessesByCommandMatch -Pattern $Service.CommandMatch -ExcludeProcessIds $exclude
    $null = Stop-TbccProcessesByCommandMatch -Pattern ('py\.exe.*' + $Service.CommandMatch) -ExcludeProcessIds $exclude
    Start-Sleep -Milliseconds 400
  }

  if (-not $Force -and (Test-TbccServiceProcessRunning -Service $Service)) {
    return
  }

  $hubReady = $false
  if ($UseErrorHubWrapper) {
    $hubPath = Join-Path $TbccRoot "scripts\tbcc-error-hub.ps1"
    if (Test-Path -LiteralPath $hubPath) {
      . $hubPath
      $null = Register-TbccServiceLauncher -TbccRoot $TbccRoot -ServiceName $Service.Title -Command $cmd
      $hubReady = $true
    }
  }

  $wtHost = Get-TbccWtHostPid -TbccRoot $TbccRoot
  $useHeadless = $Background -or (
    (Test-TbccBackgroundServiceStartEnabled -TbccRoot $TbccRoot) -and -not $wtHost
  )
  if ($useHeadless) {
    $null = Start-TbccStackServiceHeadless -Service $Service -TbccRoot $TbccRoot `
      -UseErrorHubWrapper:($hubReady) -Command $cmd
    return
  }

  $run = if ($hubReady) {
    Get-TbccServiceWrapperCmd -TbccRoot $TbccRoot -ServiceName $Service.Title
  } else { $cmd }

  if (Start-TbccWtTab -TbccRoot $TbccRoot -Title $Service.Title -Command $run -WtHostPid $(if ($wtHost) { $wtHost } else { 0 })) {
    return
  }

  if ($hubReady) {
    $runner = Join-Path $TbccRoot "scripts\run-tbcc-service.ps1"
    Start-Process -FilePath "powershell.exe" -ArgumentList @(
      '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
      '-File', $runner, '-TbccRoot', $TbccRoot, '-ServiceName', $Service.Title
    ) -WindowStyle Minimized
    return
  }

  $prefs = Get-TbccTerminalWindowPrefs -TbccRoot $TbccRoot
  $part1 = "mode con: cols=$($prefs.Cols) lines=$($prefs.Lines)"
  $part2 = 'title "' + $Service.Title + '"'
  $part3 = $run
  $full = $part1 + " & " + $part2 + " & " + $part3
  Start-Process -FilePath $env:ComSpec -ArgumentList @("/c", $full) -WindowStyle Minimized
}

function Get-TbccSecretaryStackService {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $py = Get-TbccControlPythonCmd
  $backendDir = Join-Path $TbccRoot "backend"
  $dotEnv = Read-TbccControlDotEnv -Path (Join-Path $TbccRoot ".env")
  $token = ($dotEnv["TBCC_SECRETARY_BOT_TOKEN"] -as [string]).Trim()
  if (-not $token) { $token = ($dotEnv["SECRETARY_BOT_TOKEN"] -as [string]).Trim() }
  if (-not $token) { return $null }
  return [pscustomobject]@{
    Id = "secretary"
    Title = "TBCC-SecretaryBot"
    Port = 0
    CommandMatch = "bots\.secretary_bot"
    Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m bots.secretary_bot')
  }
}

function Restart-TbccSecretaryBot {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$UseErrorHubWrapper
  )
  $svc = Get-TbccSecretaryStackService -TbccRoot $TbccRoot
  if (-not $svc) { throw "TBCC_SECRETARY_BOT_TOKEN not set in tbcc/.env" }
  $null = Stop-TbccStackService -Service $svc -TbccRoot $TbccRoot
  Start-Sleep -Milliseconds 800
  Start-TbccStackService -Service $svc -TbccRoot $TbccRoot -UseErrorHubWrapper:$UseErrorHubWrapper
  return $svc
}

function Restart-TbccStackService {
  param(
    [Parameter(Mandatory = $true)][string]$ServiceId,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [switch]$UseErrorHubWrapper,
    [switch]$Background
  )
  $svc = Get-TbccStackServiceById -ServiceId $ServiceId -TbccRoot $TbccRoot -FullStack:$FullStack -MenuCatalog
  if (-not $svc) { throw ("Unknown service id: " + $ServiceId) }
  if ($ServiceId -eq "backend") {
    $null = Set-TbccBackendRestartGrace -TbccRoot $TbccRoot
  }
  $null = Stop-TbccStackService -Service $svc -TbccRoot $TbccRoot -GracefulTabClose
  if ($TbccRoot -and (Get-Command Wait-TbccServiceTabClosed -ErrorAction SilentlyContinue)) {
    $gone = Wait-TbccServiceTabClosed -Title $svc.Title -TbccRoot $TbccRoot -MaxWaitSeconds 10
    if (-not $gone -and (Get-Command Invoke-TbccCloseServiceTab -ErrorAction SilentlyContinue)) {
      $hub = Join-Path $TbccRoot "scripts\tbcc-error-hub.ps1"
      if (Test-Path -LiteralPath $hub) { . $hub }
      $null = Invoke-TbccCloseServiceTab -TbccRoot $TbccRoot -ServiceName $svc.Title
      Start-Sleep -Milliseconds 400
    }
  } else {
    Start-Sleep -Milliseconds 1500
  }
  $still = Test-TbccServiceProcessRunning -Service $svc
  if ($still) {
    $null = Stop-TbccStackService -Service $svc -TbccRoot $TbccRoot
    Start-Sleep -Milliseconds 800
  }
  Start-TbccStackService -Service $svc -TbccRoot $TbccRoot -UseErrorHubWrapper:$UseErrorHubWrapper -Force -Background:$Background
  if ($ServiceId -eq "backend") {
    $up = Wait-TbccBackendHealth -TimeoutSec 90
    if ($up) {
      $null = Clear-TbccBackendRestartGrace -TbccRoot $TbccRoot
    }
  }
  return $svc
}

function Stop-TbccTelegramSessionContenders {
  <#
  Processes that contend with the API/Celery on admin.session (or add Telethon load).
  Not started by start.ps1 -Full; often left over from manual runs or old tabs.
  #>
  $killed = @()
  $patterns = @(
    '-m\s+bots\.scraper_bot',
    'bots\\scraper_bot',
    'run_scrape_once\.py',
    '-m\s+bots\.admin_bot',
    'bots\\admin_bot',
    'admin_bot\.py'
  )
  foreach ($pat in $patterns) {
    $killed += @(Stop-TbccProcessesByCommandMatch -Pattern $pat)
  }
  return @($killed | Select-Object -Unique)
}

function Stop-TbccAllStackServices {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack
  )
  $all = Get-TbccStackServices -TbccRoot $TbccRoot -FullStack:$FullStack
  $killed = @()
  foreach ($svc in ($all | Sort-Object { $_.Port } -Descending)) {
    $killed += @(Stop-TbccStackService -Service $svc -TbccRoot $TbccRoot)
  }
  return @($killed | Select-Object -Unique)
}

function Get-TbccSupervisorProcessIds {
  $ids = New-Object 'System.Collections.Generic.HashSet[int]'
  try {
    foreach ($proc in Get-CimInstance Win32_Process -ErrorAction SilentlyContinue) {
      $cmd = [string]$proc.CommandLine
      if (-not $cmd) { continue }
      if ($cmd -match 'tbcc-supervisor\.ps1') {
        foreach ($treePid in (Get-TbccProcessTreePids -RootPid $proc.ProcessId)) {
          [void]$ids.Add($treePid)
        }
      }
    }
  } catch {}
  return @($ids)
}

function Test-TbccProcessCommandIsTbcc {
  param([string]$CommandLine, [string]$TbccRoot)
  if (-not $CommandLine) { return $false }
  # Tray / ops scripts must never be killed by stack stop (path under tbcc would match otherwise).
  if ($CommandLine -match 'tbcc-supervisor\.ps1|tbcc-launch-daemon\.ps1|tbcc-cold-start\.ps1|tbcc-restart-full-stack\.ps1|register-supervisor-autostart\.ps1|tbcc-cleanup-orphans\.ps1|tbcc-stack-preflight\.ps1') {
    return $false
  }
  if ($CommandLine -match 'title\s+"(TBCC-|AOF-Forum)') { return $true }
  if ($CommandLine -match '--title\s+(TBCC-|AOF-Forum)') { return $true }
  if ($CommandLine -match 'run-tbcc-service\.ps1|tbcc-error-hub\.ps1|show-tbcc-error-hub|run-tbcc-stackwatch\.ps1|show-tbcc-processes\.ps1|tbcc-restart-full-stack\.ps1') {
    return $true
  }
  if ($TbccRoot) {
    $esc = [regex]::Escape($TbccRoot)
    if ($CommandLine -match ($esc + '\\start\.ps1')) { return $true }
    if ($CommandLine -match ($esc + '\\backend\\') -and $CommandLine -match 'uvicorn|celery|bots\\') { return $true }
    if ($CommandLine -match ($esc + '\\backend\\') -and $CommandLine -match 'app\.(main|workers)') { return $true }
    if ($CommandLine -match ($esc + '\\dashboard\\') -and $CommandLine -match 'vite|npm') { return $true }
    if ($CommandLine -match 'uvicorn\s+app\.main:app') { return $true }
    if ($CommandLine -match 'celery\s+-A\s+app\.workers') { return $true }
  }
  return $false
}

function Get-TbccProcessTreePids {
  param(
    [Parameter(Mandatory = $true)][int]$RootPid,
    $AllProcesses = $null
  )
  if (-not $AllProcesses) {
    $AllProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  }
  $seen = New-Object 'System.Collections.Generic.HashSet[int]'
  $queue = [System.Collections.Queue]::new()
  [void]$seen.Add($RootPid)
  $queue.Enqueue($RootPid)
  while ($queue.Count -gt 0) {
    $parent = $queue.Dequeue()
    foreach ($proc in $AllProcesses) {
      if ($proc.ParentProcessId -eq $parent -and -not $seen.Contains($proc.ProcessId)) {
        [void]$seen.Add($proc.ProcessId)
        $queue.Enqueue($proc.ProcessId)
      }
    }
  }
  return @($seen)
}

function Get-TbccWindowsTerminalHostPids {
  param(
    [string]$TbccRoot,
    [int[]]$ExcludeProcessIds = @()
  )
  $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  if ($all.Count -eq 0) { return @() }

  $hosts = New-Object 'System.Collections.Generic.HashSet[int]'
  foreach ($proc in $all) {
    if ($ExcludeProcessIds -contains $proc.ProcessId) { continue }
    $name = [string]$proc.Name
    $cmd = [string]$proc.CommandLine
    # Only TBCC-named tab hosts — do not kill every Windows Terminal that has a random tab cwd under tbcc.
    if ($name -ieq 'wt.exe') {
      if ($cmd -match '--title\s+(TBCC-|AOF-Forum)|"TBCC-') {
        [void]$hosts.Add($proc.ProcessId)
      }
      continue
    }
    # WindowsTerminal.exe: rely on .tbcc-run pid files from start.ps1 (no broad tree heuristic).
  }
  return @($hosts)
}

function Stop-TbccProcessTree {
  param(
    [int]$ProcessId,
    [int[]]$ExcludeProcessIds = @(),
    $AllProcesses = $null
  )
  if ($ProcessId -le 4) { return }
  if ($ExcludeProcessIds -contains $ProcessId) { return }
  if (-not $AllProcesses) {
    $AllProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  }
  $root = $AllProcesses | Where-Object { $_.ProcessId -eq $ProcessId } | Select-Object -First 1
  if (-not $root) { return }
  if (Test-TbccProcessIsIdeShellHost -Process $root -AllProcesses $AllProcesses -IdeProtected $ExcludeProcessIds) { return }
  $tree = @(Get-TbccProcessTreePids -RootPid $ProcessId -AllProcesses $AllProcesses)
  foreach ($tp in $tree) {
    if ($ExcludeProcessIds -contains $tp) { return }
  }
  $shellNames = @('powershell.exe', 'pwsh.exe', 'cmd.exe')
  if ($shellNames -contains [string]$root.Name) {
    if (-not (Test-TbccProcessIsTbccManagedShell -CommandLine ([string]$root.CommandLine))) { return }
  }
  if (-not (Test-TbccProcessIsTbccWtHost -Process $root)) {
    if ([string]$root.Name -in @('wt.exe', 'WindowsTerminal.exe')) { return }
  }
  try {
    & taskkill.exe /PID $ProcessId /T /F 2>$null | Out-Null
  } catch {
    try { Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue } catch {}
  }
}

function Stop-TbccWindowsTerminalHosts {
  param(
    [string]$TbccRoot,
    [int[]]$ExcludeProcessIds = @()
  )
  $runDir = Join-Path $TbccRoot ".tbcc-run"
  foreach ($pidName in @('wt-tab-host.pid', 'windows-terminal-host.pid')) {
    $pidFile = Join-Path $runDir $pidName
    if (-not (Test-Path -LiteralPath $pidFile)) { continue }
    try {
      $oldPid = [int]((Get-Content -LiteralPath $pidFile -Raw -ErrorAction Stop).Trim())
      if ($oldPid -gt 4 -and ($ExcludeProcessIds -notcontains $oldPid)) {
        $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
        $oldProc = $all | Where-Object { $_.ProcessId -eq $oldPid } | Select-Object -First 1
        if ($oldProc -and ((Test-TbccProcessIsTbccWtHost -Process $oldProc) -or (Test-TbccProcessIsTbccManagedShell -CommandLine ([string]$oldProc.CommandLine)))) {
          Stop-TbccProcessTree -ProcessId $oldPid -ExcludeProcessIds $ExcludeProcessIds -AllProcesses $all
        }
      }
    } catch {}
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
  }

  $null = Stop-TbccProcessesByCommandMatch -Pattern 'wt\.exe.*(--title\s+TBCC-|TBCC-Backend)' -ExcludeProcessIds $ExcludeProcessIds
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'WindowsTerminal\.exe.*(--title\s+TBCC-|TBCC-Backend)' -ExcludeProcessIds $ExcludeProcessIds

  foreach ($hostPid in (Get-TbccWindowsTerminalHostPids -TbccRoot $TbccRoot -ExcludeProcessIds $ExcludeProcessIds)) {
    Stop-TbccProcessTree -ProcessId $hostPid -ExcludeProcessIds $ExcludeProcessIds
  }
}

function Wait-TbccPriorStackGone {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [int[]]$ExcludeProcessIds = @(),
    [int]$MaxWaitSeconds = 45
  )
  $services = Get-TbccStackServices -TbccRoot $TbccRoot -FullStack:$FullStack
  $ports = @($services | Where-Object { $_.Port -gt 0 } | ForEach-Object { $_.Port } | Select-Object -Unique)
  $deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
  while ((Get-Date) -lt $deadline) {
    $busy = $false
    foreach ($p in $ports) {
      if (Test-TbccPortListening -Port $p) { $busy = $true; break }
    }
    if (-not $busy) {
      foreach ($svc in $services) {
        if (Test-TbccServiceProcessRunning -Service $svc) { $busy = $true; break }
      }
    }
    if (-not $busy) {
      $wt = @(Get-TbccWindowsTerminalHostPids -TbccRoot $TbccRoot -ExcludeProcessIds $ExcludeProcessIds)
      if ($wt.Count -eq 0) { return $true }
      $busy = $true
    }
    Start-Sleep -Milliseconds 400
  }
  return $false
}

function Register-TbccWtTabHostFromLauncher {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][int]$LauncherPid
  )
  $runDir = Join-Path $TbccRoot ".tbcc-run"
  if (-not (Test-Path -LiteralPath $runDir)) {
    New-Item -ItemType Directory -Path $runDir -Force | Out-Null
  }
  Set-Content -LiteralPath (Join-Path $runDir "wt-tab-host.pid") -Value $LauncherPid -Encoding ascii -NoNewline
  Start-Sleep -Milliseconds 700
  $hosts = @(Get-TbccWindowsTerminalHostPids -TbccRoot $TbccRoot)
  if ($hosts.Count -gt 0) {
    Set-Content -LiteralPath (Join-Path $runDir "windows-terminal-host.pid") -Value $hosts[0] -Encoding ascii -NoNewline
  }
}

function Stop-TbccPriorStackWindows {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [int[]]$ExcludeProcessIds = @(),
    [switch]$Wait,
    [int]$MaxWaitSeconds = 45
  )
  $exclude = @(Get-TbccStopExcludeProcessIds -Extra $ExcludeProcessIds)
  $hubScript = Join-Path $TbccRoot "scripts\tbcc-error-hub.ps1"
  if (Test-Path -LiteralPath $hubScript) {
    . $hubScript
    $null = Stop-TbccStackGracefully -TbccRoot $TbccRoot -FullStack:$FullStack -ExcludeProcessIds $exclude
  } else {
    $null = Stop-TbccAllStackServices -TbccRoot $TbccRoot -FullStack:$FullStack
  }
  Stop-TbccWindowsTerminalHosts -TbccRoot $TbccRoot -ExcludeProcessIds $exclude

  $allProcs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  # Only TBCC-titled external shells — never blanket-kill start.ps1 (would hit IDE terminals with tbcc cwd).
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'title\s+"(TBCC-|AOF-Forum|OpenClaw-Gateway)' -ExcludeProcessIds $exclude
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'run-tbcc-service\.ps1' -ExcludeProcessIds $exclude
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'tbcc-error-hub\.ps1' -ExcludeProcessIds $exclude
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'show-tbcc-error-hub' -ExcludeProcessIds $exclude
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'run-tbcc-stackwatch\.ps1|show-tbcc-processes\.ps1' -ExcludeProcessIds $exclude

  try {
    $procs = $allProcs |
      Where-Object { $_.CommandLine -and (Test-TbccProcessCommandIsTbcc -CommandLine $_.CommandLine -TbccRoot $TbccRoot) }
    foreach ($pr in $procs) {
      if ($exclude -contains $pr.ProcessId) { continue }
      if (Test-TbccProcessIsIdeShellHost -Process $pr -AllProcesses $allProcs -IdeProtected $exclude) { continue }
      $shellNames = @('powershell.exe', 'pwsh.exe', 'cmd.exe')
      if ($shellNames -contains [string]$pr.Name) {
        if (-not (Test-TbccProcessIsTbccManagedShell -CommandLine ([string]$pr.CommandLine))) { continue }
      }
      Stop-TbccProcessTree -ProcessId $pr.ProcessId -ExcludeProcessIds $exclude -AllProcesses $allProcs
    }
  } catch {}

  # Second pass: tab shells can outlive a partial kill.
  Stop-TbccWindowsTerminalHosts -TbccRoot $TbccRoot -ExcludeProcessIds $exclude

  $stray = @(Stop-TbccStrayStackProcesses -TbccRoot $TbccRoot -ExcludeProcessIds $exclude)

  $cleanupOrphans = Join-Path $TbccRoot "scripts\tbcc-cleanup-orphans.ps1"
  if (Test-Path -LiteralPath $cleanupOrphans) {
    try {
      Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $cleanupOrphans
      ) -WindowStyle Hidden -Wait | Out-Null
    } catch {}
  }

  if ($Wait) {
    return (Wait-TbccPriorStackGone -TbccRoot $TbccRoot -FullStack:$FullStack -ExcludeProcessIds $exclude -MaxWaitSeconds $MaxWaitSeconds)
  }
  return $true
}

function Invoke-TbccColdStart {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$NoOpenBrowser,
    [switch]$SkipDocker,
    [switch]$SkipDeps,
    [switch]$SkipMigrations,
    [switch]$SkipPriorStop
  )
  if ($SkipDocker -or $SkipDeps -or $SkipMigrations -or $SkipPriorStop) {
    Write-Warning "Invoke-TbccColdStart: SkipDocker/SkipDeps/SkipMigrations/SkipPriorStop are ignored; orchestrator runs start.ps1 -Full -WtTabs."
  }
  Invoke-TbccOrchestrateInWt -TbccRoot $TbccRoot -Action ColdStart -NoOpen:$NoOpenBrowser
}

function Invoke-TbccStackLaunch {
  <#
  Default TBCC cold start (16GB-friendly): API, dashboard, Celery, core bots, mandatory Album Composer.
  Skips forum, macro search, admin/companion, enrichment sidecars unless enabled in tray Services.
  #>
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$NoOpenBrowser
  )
  Set-TbccStackProfile -TbccRoot $TbccRoot -Profile lean | Out-Null
  Invoke-TbccOrchestrateInWt -TbccRoot $TbccRoot -Action ColdStart -NoOpen:$NoOpenBrowser
}

function Invoke-TbccFullStackLaunch {
  <# Advanced: full profile — optional bots + enrichment sidecars when installed. #>
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$NoOpenBrowser
  )
  Set-TbccStackProfile -TbccRoot $TbccRoot -Profile full | Out-Null
  Invoke-TbccOrchestrateInWt -TbccRoot $TbccRoot -Action ColdStart -NoOpen:$NoOpenBrowser
}

function Invoke-TbccColdStartFromTray {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$NoOpenBrowser
  )
  Invoke-TbccStackLaunch -TbccRoot $TbccRoot -NoOpenBrowser:$NoOpenBrowser
}

function Invoke-TbccLeanStackLaunch {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$NoOpenBrowser
  )
  Invoke-TbccStackLaunch -TbccRoot $TbccRoot -NoOpenBrowser:$NoOpenBrowser
}

function Invoke-TbccRestartStack {
  <# Stop all TBCC tabs, then relaunch only services that were running (profile unchanged). #>
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  Invoke-TbccOrchestrateInWt -TbccRoot $TbccRoot -Action Restart -NoOpen
}

function Invoke-TbccRestartFullStack {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  Invoke-TbccRestartStack -TbccRoot $TbccRoot
}

function Invoke-TbccStopFullStack {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  Invoke-TbccOrchestrateInWt -TbccRoot $TbccRoot -Action Stop
}

function Invoke-TbccRestartApiPayment {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $script = Join-Path $TbccRoot "restart-api-payment.ps1"
  if (-not (Test-Path -LiteralPath $script)) { throw "Missing restart-api-payment.ps1" }
  Start-Process -FilePath (Get-TbccLaunchPowerShellExe) -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $script
  ) -WorkingDirectory $TbccRoot -WindowStyle Normal
}
