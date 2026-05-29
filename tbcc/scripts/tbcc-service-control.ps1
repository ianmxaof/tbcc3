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

function Test-TbccControlLocalUrl {
  param([string]$Url)
  if (-not $Url) { return $false }
  try {
    $h = ([Uri]$Url).Host.ToLower()
    return ($h -eq "127.0.0.1" -or $h -eq "localhost")
  } catch { return $false }
}

function Stop-TbccListenersOnPort {
  param([int]$Port)
  $killed = @()
  if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
    $pids = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($p in $pids) {
      if ($p -and $p -gt 4) {
        try { Stop-Process -Id $p -Force -ErrorAction Stop; $killed += $p } catch {}
      }
    }
  }
  if ($killed.Count -eq 0) {
    $raw = netstat -ano 2>$null | Select-String (":$Port\s")
    foreach ($line in $raw) {
      if ($line -match '\s+(\d+)\s*$') {
        $procId = [int]$Matches[1]
        if ($procId -gt 4) {
          try { Stop-Process -Id $procId -Force -ErrorAction Stop; $killed += $procId } catch {}
        }
      }
    }
  }
  return $killed
}

function Stop-TbccProcessesByCommandMatch {
  param(
    [string]$Pattern,
    [int[]]$ExcludeProcessIds = @()
  )
  $killed = @()
  try {
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object { $_.CommandLine -and ($_.CommandLine -match $Pattern) }
    foreach ($pr in $procs) {
      if ($ExcludeProcessIds -contains $pr.ProcessId) { continue }
      try { Stop-Process -Id $pr.ProcessId -Force -ErrorAction Stop; $killed += $pr.ProcessId } catch {}
    }
  } catch {}
  return $killed
}

function Stop-TbccProcessesByServiceTitle {
  param([string]$Title, [string]$TbccRoot)
  $killed = @()
  $safe = ($Title -replace '[^\w\-]', '_')
  $pat = 'run-tbcc-service\.ps1.*-ServiceName\s+' + [regex]::Escape($Title)
  $killed += @(Stop-TbccProcessesByCommandMatch -Pattern $pat)
  $pat2 = 'run-tbcc-service\.ps1.*-ServiceName\s+' + [regex]::Escape('"' + $Title + '"')
  $killed += @(Stop-TbccProcessesByCommandMatch -Pattern $pat2)
  return @($killed | Select-Object -Unique)
}

function Get-TbccStackServices {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack
  )
  $py = Get-TbccControlPythonCmd
  $backendDir = Join-Path $TbccRoot "backend"
  $dashboardDir = Join-Path $TbccRoot "dashboard"
  $aofForumDir = Join-Path (Split-Path $TbccRoot -Parent) "aof-forum"
  $servicesDir = Join-Path $TbccRoot "services"
  $hasForum = Test-Path (Join-Path $aofForumDir "package.json")
  $dotEnv = Read-TbccControlDotEnv -Path (Join-Path $TbccRoot ".env")

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
      Id = "dashboard"; Title = "TBCC-Dashboard"; Port = 5173; CommandMatch = "vite|npm run dev";
      Command = ('cd /d "' + $dashboardDir + '" & npm run dev')
    })
  if ($hasForum) {
    [void]$list.Add([pscustomobject]@{
        Id = "forum"; Title = "AOF-Forum"; Port = 3001; CommandMatch = "next dev|aof-forum";
        Command = ('cd /d "' + $aofForumDir + '" & npm run dev')
      })
  }

  if ($FullStack) {
    [void]$list.Add([pscustomobject]@{
        Id = "celery"; Title = "TBCC-Celery"; Port = 0; CommandMatch = "celery.*worker|app\.workers\.celery_app worker";
        Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m celery -A app.workers.celery_app worker -l info -P solo -Q celery,post,scrape,subscription,telegram')
      })
    [void]$list.Add([pscustomobject]@{
        Id = "beat"; Title = "TBCC-Beat"; Port = 0; CommandMatch = "celery.*beat|app\.workers\.celery_app beat";
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
    [void]$list.Add([pscustomobject]@{
        Id = "loot"; Title = "TBCC-LootBot"; Port = 0; CommandMatch = "bots\.loot_bot";
        Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m bots.loot_bot')
      })
  }

  $nsfwUrl = $dotEnv["TBCC_NSFW_DETECT_URL"]
  if ((Test-TbccControlLocalUrl $nsfwUrl) -and (Test-Path (Join-Path $servicesDir "run_nsfw_detect.py"))) {
    [void]$list.Add([pscustomobject]@{
        Id = "nsfw"; Title = "TBCC-NSFW-Detect"; Port = 8001; CommandMatch = "run_nsfw_detect";
        Command = ('cd /d "' + $servicesDir + '" & ' + $py + ' run_nsfw_detect.py')
      })
  }

  $lustUrl = $dotEnv["TBCC_LUSTPRESS_URL"]
  $lustDir = Join-Path $servicesDir "lustpress"
  if ((Test-TbccControlLocalUrl $lustUrl) -and (Test-Path (Join-Path $lustDir "package.json"))) {
    $bun = $null
    try { $bun = (Get-Command "bun" -ErrorAction Stop).Source } catch {}
    if (-not $bun) {
      $bun = Join-Path $env:USERPROFILE ".bun\bin\bun.exe"
    }
    if ($bun -and (Test-Path -LiteralPath $bun)) {
      $bunQ = '"' + $bun + '"'
      [void]$list.Add([pscustomobject]@{
          Id = "lustpress"; Title = "TBCC-Lustpress"; Port = 3000; CommandMatch = "lustpress|bun.*start";
          Command = ('cd /d "' + $lustDir + '" & ' + $bunQ + ' run start:dev')
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

function Test-TbccPortListening {
  param([int]$Port)
  if ($Port -le 0) { return $false }
  try {
    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
      return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    }
  } catch {}
  return [bool](netstat -ano 2>$null | Select-String (":$Port\s"))
}

function Test-TbccServiceProcessRunning {
  param($Service)
  if ($Service.Port -gt 0 -and (Test-TbccPortListening -Port $Service.Port)) { return $true }
  if (-not $Service.CommandMatch) { return $false }
  $alive = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and ($_.CommandLine -match $Service.CommandMatch) })
  return ($alive.Count -gt 0)
}

function Get-TbccServiceStatusLabel {
  param($Service)
  if (Test-TbccServiceProcessRunning -Service $Service) { return "up" }
  return "down"
}

function Stop-TbccStackService {
  param(
    [Parameter(Mandatory = $true)]$Service,
    [string]$TbccRoot
  )
  $killed = @()
  if ($Service.Port -gt 0) {
    $killed += @(Stop-TbccListenersOnPort -Port $Service.Port)
  }
  if ($Service.CommandMatch) {
    $killed += @(Stop-TbccProcessesByCommandMatch -Pattern $Service.CommandMatch)
  }
  if ($TbccRoot) {
    $killed += @(Stop-TbccProcessesByServiceTitle -Title $Service.Title -TbccRoot $TbccRoot)
  }
  return @($killed | Select-Object -Unique)
}

function Start-TbccStackService {
  param(
    [Parameter(Mandatory = $true)]$Service,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$UseErrorHubWrapper
  )
  $cmd = $Service.Command
  if (-not $cmd) { throw ("No command for service " + $Service.Title) }

  $run = $cmd
  if ($UseErrorHubWrapper) {
    $hubPath = Join-Path $TbccRoot "scripts\tbcc-error-hub.ps1"
    if (Test-Path -LiteralPath $hubPath) {
      . $hubPath
      $null = Register-TbccServiceLauncher -TbccRoot $TbccRoot -ServiceName $Service.Title -Command $cmd
      $run = Get-TbccServiceWrapperCmd -TbccRoot $TbccRoot -ServiceName $Service.Title
    }
  }

  $part1 = "mode con: cols=100 lines=28"
  $part2 = 'title "' + $Service.Title + '"'
  $part3 = $run
  $full = $part1 + " & " + $part2 + " & " + $part3
  Start-Process -FilePath $env:ComSpec -ArgumentList @("/k", $full) -WindowStyle Normal
}

function Restart-TbccStackService {
  param(
    [Parameter(Mandatory = $true)][string]$ServiceId,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [switch]$UseErrorHubWrapper
  )
  $svc = Get-TbccStackServices -TbccRoot $TbccRoot -FullStack:$FullStack |
    Where-Object { $_.Id -eq $ServiceId } | Select-Object -First 1
  if (-not $svc) { throw ("Unknown service id: " + $ServiceId) }
  $null = Stop-TbccStackService -Service $svc -TbccRoot $TbccRoot
  Start-Sleep -Seconds 1
  Start-TbccStackService -Service $svc -TbccRoot $TbccRoot -UseErrorHubWrapper:$UseErrorHubWrapper
  return $svc
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
  if ($CommandLine -match 'run-tbcc-service\.ps1|tbcc-error-hub\.ps1|show-tbcc-error-hub|tbcc-restart-full-stack\.ps1') {
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
  param([int]$ProcessId)
  if ($ProcessId -le 4) { return }
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
        Stop-TbccProcessTree -ProcessId $oldPid
      }
    } catch {}
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
  }

  $null = Stop-TbccProcessesByCommandMatch -Pattern 'wt\.exe.*(--title\s+TBCC-|TBCC-Backend)' -ExcludeProcessIds $ExcludeProcessIds
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'WindowsTerminal\.exe.*(--title\s+TBCC-|TBCC-Backend)' -ExcludeProcessIds $ExcludeProcessIds

  foreach ($hostPid in (Get-TbccWindowsTerminalHostPids -TbccRoot $TbccRoot -ExcludeProcessIds $ExcludeProcessIds)) {
    Stop-TbccProcessTree -ProcessId $hostPid
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
  $exclude = @($ExcludeProcessIds) + @(Get-TbccSupervisorProcessIds) | Select-Object -Unique
  $null = Stop-TbccAllStackServices -TbccRoot $TbccRoot -FullStack:$FullStack
  Stop-TbccWindowsTerminalHosts -TbccRoot $TbccRoot -ExcludeProcessIds $exclude

  $esc = [regex]::Escape($TbccRoot)
  # Other start.ps1 hosts only (never the live launcher — pass -ExcludeProcessIds @($PID) from start.ps1).
  $null = Stop-TbccProcessesByCommandMatch -Pattern ($esc + '.*start\.ps1') -ExcludeProcessIds $exclude
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'run-tbcc-service\.ps1' -ExcludeProcessIds $exclude
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'tbcc-error-hub\.ps1' -ExcludeProcessIds $exclude
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'show-tbcc-error-hub' -ExcludeProcessIds $exclude

  try {
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object { $_.CommandLine -and (Test-TbccProcessCommandIsTbcc -CommandLine $_.CommandLine -TbccRoot $TbccRoot) }
    foreach ($pr in $procs) {
      if ($exclude -contains $pr.ProcessId) { continue }
      Stop-TbccProcessTree -ProcessId $pr.ProcessId
    }
  } catch {}

  # Second pass: tab shells can outlive a partial kill.
  Stop-TbccWindowsTerminalHosts -TbccRoot $TbccRoot -ExcludeProcessIds $exclude

  $cleanupOrphans = Join-Path $TbccRoot "scripts\tbcc-cleanup-orphans.ps1"
  if (Test-Path -LiteralPath $cleanupOrphans) {
    try { & powershell -NoProfile -ExecutionPolicy Bypass -File $cleanupOrphans 2>$null | Out-Null } catch {}
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
  if (-not $SkipPriorStop) {
    $gone = Stop-TbccPriorStackWindows -TbccRoot $TbccRoot -FullStack -Wait -MaxWaitSeconds 60
    if (-not $gone) {
      Write-Warning "Prior TBCC stack did not fully exit within 60s (ports or Windows Terminal tabs may still be up). Starting anyway."
    }
  }

  $preflightScript = Join-Path $TbccRoot "scripts\tbcc-stack-preflight.ps1"
  if (Test-Path -LiteralPath $preflightScript) {
    . $preflightScript
    $pf = Test-TbccStackPreflight -TbccRoot $TbccRoot
    if (-not $pf.ok) {
      foreach ($issue in $pf.issues) { Write-Warning "Preflight: $issue" }
    }
  }

  $startPs1 = Join-Path $TbccRoot "start.ps1"
  if (-not (Test-Path -LiteralPath $startPs1)) { throw "Missing start.ps1" }
  # -NoExit keeps the launcher window open after Docker/migrations so you can read output;
  # service tabs open separately in Windows Terminal (-WtTabs).
  $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-File", $startPs1, "-Full", "-WtTabs")
  if ($NoOpenBrowser) { $args += "-NoOpen" }
  if ($SkipDocker) { $args += "-SkipDocker" }
  if ($SkipDeps) { $args += "-SkipDeps" }
  if ($SkipMigrations) { $args += "-SkipMigrations" }
  Start-Process -FilePath (Get-TbccLaunchPowerShellExe) -ArgumentList $args -WorkingDirectory $TbccRoot -WindowStyle Normal
}

# Tray-safe: stop+start in a separate window so the supervisor process is never killed by Stop-TbccPriorStackWindows.
function Invoke-TbccColdStartFromTray {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$NoOpenBrowser
  )
  $launcher = Join-Path $TbccRoot "scripts\tbcc-cold-start.ps1"
  if (-not (Test-Path -LiteralPath $launcher)) { throw "Missing tbcc-cold-start.ps1" }
  $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-File", $launcher)
  if ($NoOpenBrowser) { $argList += "-NoOpen" }
  Start-Process -FilePath (Get-TbccLaunchPowerShellExe) -ArgumentList $argList -WorkingDirectory $TbccRoot -WindowStyle Normal
}

function Invoke-TbccRestartFullStack {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $restartPs1 = Join-Path $TbccRoot "scripts\tbcc-restart-full-stack.ps1"
  if (-not (Test-Path -LiteralPath $restartPs1)) { throw "Missing tbcc-restart-full-stack.ps1" }
  Start-Process -FilePath (Get-TbccLaunchPowerShellExe) -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-File", $restartPs1
  ) -WorkingDirectory $TbccRoot -WindowStyle Normal
}

function Invoke-TbccRestartApiPayment {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  $script = Join-Path $TbccRoot "restart-api-payment.ps1"
  if (-not (Test-Path -LiteralPath $script)) { throw "Missing restart-api-payment.ps1" }
  Start-Process -FilePath (Get-TbccLaunchPowerShellExe) -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $script
  ) -WorkingDirectory $TbccRoot -WindowStyle Normal
}
