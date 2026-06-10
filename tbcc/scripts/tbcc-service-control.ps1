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
  if ($CommandLine -match 'tbcc-stop-full-stack\.ps1|tbcc-cold-start\.ps1|tbcc-restart-full-stack\.ps1') { return $true }
  return $false
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
  param([string]$Title, [string]$TbccRoot)
  $killed = @()
  $pat = 'run-tbcc-service\.ps1.*-ServiceName\s+' + [regex]::Escape($Title)
  $killed += @(Stop-TbccProcessesByCommandMatch -Pattern $pat)
  $pat2 = 'run-tbcc-service\.ps1.*-ServiceName\s+' + [regex]::Escape('"' + $Title + '"')
  $killed += @(Stop-TbccProcessesByCommandMatch -Pattern $pat2)
  $pat3 = 'title\s+"' + [regex]::Escape($Title) + '"'
  $killed += @(Stop-TbccProcessesByCommandMatch -Pattern $pat3)
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
        Id = "celery"; Title = "TBCC-Celery"; Port = 0; CommandMatch = "app\.workers\.celery_app worker.*-Q celery";
        Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m celery -A app.workers.celery_app worker -l info -P solo -Q celery,scrape,subscription,telegram')
      })
    [void]$list.Add([pscustomobject]@{
        Id = "celery_post"; Title = "TBCC-Celery-Post"; Port = 0; CommandMatch = "app\.workers\.celery_app worker.*-Q post";
        Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m celery -A app.workers.celery_app worker -l info -P solo -Q post -n post@%h')
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
        Id = "macro_search"; Title = "TBCC-MacroSearchBot"; Port = 0; CommandMatch = "bots\.macro_search_bot";
        Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m bots.macro_search_bot')
      })
    [void]$list.Add([pscustomobject]@{
        Id = "loot"; Title = "TBCC-LootBot"; Port = 0; CommandMatch = "bots\.loot_bot";
        Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m bots.loot_bot')
      })
    [void]$list.Add([pscustomobject]@{
        Id = "album_composer"; Title = "TBCC-AlbumComposer"; Port = 0; CommandMatch = "bots\.album_composer_bot";
        Command = ('cd /d "' + $backendDir + '" & ' + $py + ' -m bots.album_composer_bot')
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

  $clipUrl = $dotEnv["TBCC_CLIP_CATEGORIZE_URL"]
  $clipCats = $dotEnv["TBCC_CLIP_CATEGORIES_FILE"]
  if ((Test-TbccControlLocalUrl $clipUrl) -and (Test-Path (Join-Path $servicesDir "run_clip_categorize.py"))) {
    if ($clipCats -and (Test-Path -LiteralPath $clipCats)) {
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
  $toggles = Read-TbccServiceToggles -TbccRoot $TbccRoot
  if (-not $toggles.ContainsKey($ServiceId)) { return $true }
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
  $svc = @(Get-TbccStackServices -TbccRoot $TbccRoot -FullStack | Where-Object { $_.Title -eq $Title } | Select-Object -First 1)
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
  return ($Service.Title + $portLabel)
}

function Update-TbccServiceStatusCache {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack
  )
  $services = @(Get-TbccStackServices -TbccRoot $TbccRoot -FullStack:$FullStack)
  $ports = Get-TbccListeningPortSet
  $procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
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
  $NotifyIcon.Text = ("TBCC Supervisor ({0}/{1} on)" -f $sum.EnabledUp, $sum.Enabled)
  if ($NotifyIcon.Text.Length -gt 63) {
    $NotifyIcon.Text = ("TBCC ({0}/{1} on)" -f $sum.EnabledUp, $sum.Enabled)
  }
}

function Invoke-TbccServiceMenuAction {
  param(
    [Parameter(Mandatory = $true)][string]$ServiceId,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [switch]$ForceRestart,
    [scriptblock]$OnNotify
  )
  $svc = @(Get-TbccStackServices -TbccRoot $TbccRoot -FullStack:$FullStack |
    Where-Object { $_.Id -eq $ServiceId } | Select-Object -First 1)
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
  #>
  param(
    [Parameter(Mandatory = $true)]$MenuItem,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack,
    [scriptblock]$OnNotify,
    [scriptblock]$OnChanged
  )
  Clear-TbccRestartServiceMenu -MenuItem $MenuItem
  $map = @{}
  foreach ($svc in (Get-TbccStackServices -TbccRoot $TbccRoot -FullStack:$FullStack)) {
    $item = New-Object System.Windows.Forms.ToolStripMenuItem
    $item.Text = Get-TbccServiceMenuText -Service $svc
    $item.Tag = @{ Id = $svc.Id; Title = $svc.Title; TbccUserEnabled = $true }
    $sid = $svc.Id
    [void]$item.Add_Click({
      param($sender, $e)
      $ctrl = ([System.Windows.Forms.Control]::ModifierKeys -band [System.Windows.Forms.Keys]::Control) -ne 0
      try {
        Invoke-TbccServiceMenuAction -ServiceId $sid -TbccRoot $TbccRoot -FullStack:$FullStack `
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
  $hint.Text = "Click toggle | Ctrl+click restart"
  $hint.Tag = @{ TbccMenuHint = $true; TbccUserEnabled = $false }
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
    $item.Text = $row.Text
    if (-not $item.Tag) { $item.Tag = @{} }
    $item.Tag.TbccUserEnabled = [bool]$row.UserEnabled
    $item.Tag.Running = ($row.Status -eq "up")
    $item.Enabled = $true
    if ($row.UserEnabled) {
      if ($row.Status -eq "up") {
        $item.ToolTipText = "Running - click to disable | Ctrl+click restart"
      } else {
        $item.ToolTipText = "Enabled but stopped - click to disable | Ctrl+click restart"
      }
    } else {
      $item.ToolTipText = "Disabled - click to enable"
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
    [string]$TbccRoot
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
    $killed += @(Stop-TbccProcessesByCommandMatch -Pattern $Service.CommandMatch)
  }
  if ($TbccRoot) {
    $killed += @(Stop-TbccProcessesByServiceTitle -Title $Service.Title -TbccRoot $TbccRoot)
  }
  return @($killed | Select-Object -Unique)
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
      if ($pn -ieq 'WindowsTerminal.exe' -or $pn -ieq 'wt.exe') { return $pidVal }
    } catch {}
  }
  $hosts = @(Get-TbccWindowsTerminalHostPids -TbccRoot $TbccRoot)
  if ($hosts.Count -gt 0) { return [int]$hosts[0] }
  return $null
}

function Get-TbccWtExePath {
  $wtExe = $null
  try {
    $c = Get-Command "wt.exe" -ErrorAction Stop
    $wtExe = $c.Source
  } catch {}
  if (-not $wtExe) {
    foreach ($p in @(
      (Join-Path $env:LOCALAPPDATA "Microsoft\Windows Terminal\wt.exe"),
      (Join-Path ${env:ProgramFiles} "Windows Terminal\wt.exe")
    )) {
      if (Test-Path -LiteralPath $p) { return $p }
    }
  }
  return $wtExe
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
    [switch]$NewWindow
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
    Add-TbccWtTabShellInvocation -ArgumentList $al -Title $Title -Command $Command -Cols $prefs.Cols -Lines $prefs.Lines
  } else {
    $part1 = "mode con: cols=$($prefs.Cols) lines=$($prefs.Lines)"
    $part2 = 'title "' + $Title + '"'
    $run = $part1 + ' & ' + $part2 + ' & ' + $Command
    [void]$al.Add('new-tab')
    [void]$al.Add('--title')
    [void]$al.Add($Title)
    [void]$al.Add('cmd')
    [void]$al.Add('/k')
    [void]$al.Add($run)
  }

  $proc = Start-Process -FilePath $wtExe -ArgumentList @($al.ToArray()) -WindowStyle Normal -PassThru
  if ($proc -and ($NewWindow -or -not $WtHostPid)) {
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
  <# Services/ports/WT hosts still active after a stop attempt. #>
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
  $wt = @(Get-TbccWindowsTerminalHostPids -TbccRoot $TbccRoot)
  if ($wt.Count -gt 0) {
    [void]$issues.Add(("TBCC terminal window(s) ({0})" -f $wt.Count))
  }
  return @($issues.ToArray())
}

function Get-TbccEnabledServicesDownSummary {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$FullStack
  )
  $down = New-Object System.Collections.ArrayList
  $cache = Update-TbccServiceStatusCache -TbccRoot $TbccRoot -FullStack:$FullStack
  foreach ($id in @($cache.ById.Keys)) {
    $entry = $cache.ById[$id]
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
    return "All TBCC services and terminal tabs are stopped. Safe to start again."
  }
  $left = @(Get-TbccStackResidualSummary -TbccRoot $TbccRoot -FullStack)
  if ($left.Count -eq 0) {
    return "Stop finished but some ports or processes may still be active. Check show-tbcc-processes.ps1."
  }
  $list = ($left | Select-Object -First 4) -join ", "
  if ($left.Count -gt 4) { $list += (" (+{0} more)" -f ($left.Count - 4)) }
  return ("Stop finished with issues - still active: " + $list)
}

function Build-TbccOrchestratorStartMessage {
  param(
    [Parameter(Mandatory = $true)][ValidateSet("Restart", "ColdStart")][string]$Action,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [bool]$PriorStackStopped = $true,
    [string]$StartFailure = ""
  )
  if ($StartFailure) {
    $verb = if ($Action -eq "ColdStart") { "Cold start" } else { "Restart" }
    return ($verb + " failed - " + $StartFailure)
  }
  $cache = Update-TbccServiceStatusCache -TbccRoot $TbccRoot -FullStack
  $down = @(Get-TbccEnabledServicesDownSummary -TbccRoot $TbccRoot -FullStack)
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
  Stop TBCC services one-by-one so each tab closes; keep Windows Terminal host + orchestrator tab.
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

  $services = Get-TbccStackServices -TbccRoot $TbccRoot -FullStack:$FullStack
  $ordered = @($services | Sort-Object {
    if ($_.Id -eq 'backend') { 1000 }
    elseif ($_.Port -gt 0) { 500 - $_.Port }
    else { 100 }
  })

  foreach ($svc in $ordered) {
    Write-Host ("  stopping " + $svc.Title + "...") -ForegroundColor Yellow
    $null = Stop-TbccStackService -Service $svc -TbccRoot $TbccRoot
    Start-Sleep -Milliseconds 350
  }

  $null = Stop-TbccProcessesByCommandMatch -Pattern 'run-tbcc-service\.ps1' -ExcludeProcessIds $exclude
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'show-tbcc-error-hub' -ExcludeProcessIds $exclude
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'title\s+"(TBCC-|AOF-Forum)' -ExcludeProcessIds $exclude

  foreach ($svc in ($services | Where-Object { $_.Port -gt 0 })) {
    $null = Stop-TbccListenersOnPort -Port $svc.Port -ExcludeProcessIds $exclude
  }

  $cleanupOrphans = Join-Path $TbccRoot "scripts\tbcc-cleanup-orphans.ps1"
  if (Test-Path -LiteralPath $cleanupOrphans) {
    try {
      Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $cleanupOrphans
      ) -WindowStyle Hidden -Wait | Out-Null
    } catch {}
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
  try {
    if ($hostPid) {
      $ok = Start-TbccWtTab -TbccRoot $TbccRoot -Title "TBCC-Orchestrator" -Command $cmd -WtHostPid $hostPid
    } else {
      $ok = Start-TbccWtTab -TbccRoot $TbccRoot -Title "TBCC-Orchestrator" -Command $cmd -NewWindow
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
      Add-TbccWtTabShellInvocation -ArgumentList $al -Title $Titles[$i] -Command $Commands[$i] -Cols $Cols -Lines $Lines
    } else {
      $part1 = "mode con: cols=$Cols lines=$Lines"
      $part2 = [string]::Concat('title "', $Titles[$i], '"')
      $run = [string]::Concat($part1, ' & ', $part2, ' & ', $Commands[$i])
      [void]$al.Add('new-tab')
      [void]$al.Add('--title')
      [void]$al.Add($Titles[$i])
      [void]$al.Add('cmd')
      [void]$al.Add('/k')
      [void]$al.Add($run)
    }
  }

  $proc = Start-Process -FilePath $wtExe -ArgumentList @($al.ToArray()) -WindowStyle Normal -PassThru
  if ($proc -and -not $reuseWindow) {
    Register-TbccWtTabHostFromLauncher -TbccRoot $TbccRoot -LauncherPid $proc.Id
  } elseif ($reuseWindow) {
    Refresh-TbccWtHostPid -TbccRoot $TbccRoot -PreferredPid $WtHostPid
  }
  return $true
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

  if (Start-TbccWtTab -TbccRoot $TbccRoot -Title $Service.Title -Command $run) {
    return
  }

  $prefs = Get-TbccTerminalWindowPrefs -TbccRoot $TbccRoot
  $part1 = "mode con: cols=$($prefs.Cols) lines=$($prefs.Lines)"
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
  Start-Sleep -Milliseconds 800
  Start-TbccStackService -Service $svc -TbccRoot $TbccRoot -UseErrorHubWrapper:$UseErrorHubWrapper
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
  $null = Stop-TbccAllStackServices -TbccRoot $TbccRoot -FullStack:$FullStack
  Stop-TbccWindowsTerminalHosts -TbccRoot $TbccRoot -ExcludeProcessIds $exclude

  $allProcs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  # Only TBCC-titled external shells — never blanket-kill start.ps1 (would hit IDE terminals with tbcc cwd).
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'title\s+"(TBCC-|AOF-Forum)' -ExcludeProcessIds $exclude
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'run-tbcc-service\.ps1' -ExcludeProcessIds $exclude
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'tbcc-error-hub\.ps1' -ExcludeProcessIds $exclude
  $null = Stop-TbccProcessesByCommandMatch -Pattern 'show-tbcc-error-hub' -ExcludeProcessIds $exclude

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

function Invoke-TbccColdStartFromTray {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [switch]$NoOpenBrowser
  )
  Invoke-TbccOrchestrateInWt -TbccRoot $TbccRoot -Action ColdStart -NoOpen:$NoOpenBrowser
}

function Invoke-TbccRestartFullStack {
  param([Parameter(Mandatory = $true)][string]$TbccRoot)
  Invoke-TbccOrchestrateInWt -TbccRoot $TbccRoot -Action Restart -NoOpen
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
