# TBCC Launch Script (Windows PowerShell 5.1+ and pwsh 7+). Cmd lines use single & between commands (cmd.exe).
#   .\start.ps1              — backend + dashboard; opens http://127.0.0.1:5173 in Brave if installed, else default browser
#   .\start.ps1 -NoOpen      — do not open a browser
#   .\start.ps1 -Open        — also open http://127.0.0.1:8000/docs (Swagger) in the same browser
#   .\start.ps1 -Full        — backend + dashboard + Redis + Celery + Beat + payment bot + secretary + loot overseer bot
#                            (+ NSFW Detect + Lustpress when .env URLs are localhost and repos exist under services/)
#                            (Last.fm “listening relay” has no extra exe: TBCC-Beat schedules it, TBCC-Celery post queue runs it)
#   .\start.ps1 -SkipDocker     — skip Postgres/Redis step (use when Docker DBs already running)
#   .\start.ps1 -SkipEnrichment — skip NSFW Detection API / Lustpress sidecars
#   .\start.ps1 -SkipDeps        — skip pip/npm/bun install checks (faster if you know deps are current)
#   .\start.ps1 -SkipPriorStackStop — skip in-script stop (tbcc-cold-start.ps1 already stopped the prior stack)
#   .\start.ps1 -SkipMigrations — skip alembic upgrade (rare; without it, Misc → Promo affiliate links bulk import
#                            and similar features may 500 until you run: cd backend ; python -m alembic upgrade head)
#
# Console layout (many windows are easier if smaller, or use one Terminal with tabs):
#   .\start.ps1 -CompactConsole  — smaller cmd windows (88×24 buffer) so they tile more easily
#   .\start.ps1 -WideConsole     — larger windows (140×40)
#   .\start.ps1 -WtTabs          — one Windows Terminal window, one tab per service (needs wt.exe / Windows Terminal)
#   .\start.ps1 -WtTabs -Full    — tabs: TBCC-Errors (unified log), backend, dashboard, AOF Forum (:3001), workers
#   .\start.ps1 -WtTabs -LlmChat — add tab TBCC-LlmChatBot (Ollama/OpenAI bridge; see TBCC_LLM_CHAT_BOT_TOKEN in .env)
#   .\start.ps1 -NoErrorHub      — disable TBCC-Errors tab / unified error log (services run directly in tabs)
#
# Tray supervisor (one-click cold start / per-service restart):
#   cd tbcc\tools ; .\tbcc-supervisor.ps1
# Extension cold start: tbcc-launch-daemon.ps1 on :8765 (POST /launch-full)
#   .\start.ps1 -NoReload        — uvicorn without --reload (less subprocess/socket churn; helps if Windows reports WinError 10055)
#
# When Docker is needed, the script starts Docker Desktop if the engine is not up yet (Windows).
# New windows use cmd.exe /k so they show reliably when run from Cursor / VS Code / ISE.

$ErrorActionPreference = "Continue"
$tbccDir = $PSScriptRoot

# Prefer Python 3.13 via py launcher (3.14 default on some machines has a broken pip vendor tree).
function Get-TbccPythonCmd {
  try {
    & py -3.13 -c "import sys" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { return "py -3.13" }
  } catch {}
  $py313 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"
  if (Test-Path -LiteralPath $py313) { return ('"' + $py313 + '"') }
  return "python"
}
$tbccPython = Get-TbccPythonCmd
$fullStack = $args -contains "-Full"
$skipDocker = $args -contains "-SkipDocker"
$skipEnrichment = $args -contains "-SkipEnrichment"
$skipDeps = $args -contains "-SkipDeps"
$skipMigrations = $args -contains "-SkipMigrations"
$noOpenBrowser = $args -contains "-NoOpen"
$openDocsToo = $args -contains "-Open"
$wtTabs = ($args -contains "-WtTabs") -or ($args -contains "-WindowsTerminalTabs")
$compactConsole = $args -contains "-CompactConsole"
$wideConsole = $args -contains "-WideConsole"
# Default: stable API (no --reload orphans on Windows). Opt in with -Reload when editing backend code.
$noReload = -not ($args -contains "-Reload")
$llmChat = $args -contains "-LlmChat"
$noErrorHub = $args -contains "-NoErrorHub"
$useErrorHub = -not $noErrorHub
$skipPriorStackStop = $args -contains "-SkipPriorStackStop"

# Error hub helpers must load at script scope (dot-sourcing inside a function hides them in PS 5.1).
$script:TbccErrorHubLoaded = $false
if ($useErrorHub) {
  $hubScript = Join-Path $tbccDir 'scripts\tbcc-error-hub.ps1'
  if (-not (Test-Path -LiteralPath $hubScript)) {
    throw 'Missing tbcc-error-hub.ps1 - re-pull the repo or restore tbcc\scripts\'
  }
  . $hubScript
  $script:TbccErrorHubLoaded = $true
}

$consoleCols = 100
$consoleLines = 28
if ($compactConsole) { $consoleCols = 88;  $consoleLines = 24 }
if ($wideConsole)   { $consoleCols = 140; $consoleLines = 40 }
if ($compactConsole -and $wideConsole) {
  Write-Host "  Note: -WideConsole wins over -CompactConsole." -ForegroundColor DarkYellow
  $consoleCols = 140; $consoleLines = 40
}

function Get-BraveExecutable {
  $candidates = @(
    (Join-Path $env:LOCALAPPDATA "BraveSoftware\Brave-Browser\Application\brave.exe"),
    (Join-Path ${env:ProgramFiles} "BraveSoftware\Brave-Browser\Application\brave.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "BraveSoftware\Brave-Browser\Application\brave.exe")
  )
  foreach ($p in $candidates) {
    if (Test-Path -LiteralPath $p) {
      return $p
    }
  }
  $cmd = Get-Command "brave" -ErrorAction SilentlyContinue
  if ($cmd -and $cmd.Source) {
    return $cmd.Source
  }
  return $null
}

function Open-UrlInPreferredBrowser {
  param([Parameter(Mandatory = $true)][string]$Url)
  $brave = Get-BraveExecutable
  if ($brave) {
    Start-Process -FilePath $brave -ArgumentList @($Url)
  } else {
    Start-Process $Url
  }
}

function Wait-HttpOk {
  param(
    [Parameter(Mandatory = $true)][string]$Uri,
    [int]$MaxSeconds = 50
  )
  $deadline = (Get-Date).AddSeconds($MaxSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $r = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
      if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) {
        return $true
      }
    } catch {
      # Vite still starting
    }
    Start-Sleep -Milliseconds 400
  }
  return $false
}

function Read-TbccDotEnv {
  param([Parameter(Mandatory = $true)][string]$Path)
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

function Test-LocalhostServiceUrl {
  param([string]$Url)
  if (-not $Url) { return $false }
  try {
    $u = [Uri]$Url
    $h = ($u.Host).ToLower()
    return ($h -eq "127.0.0.1" -or $h -eq "localhost")
  } catch {
    return $false
  }
}

function Get-BunExecutable {
  try {
    $c = Get-Command "bun" -ErrorAction Stop
    return $c.Source
  } catch {}
  $local = Join-Path $env:USERPROFILE ".bun\bin\bun.exe"
  if (Test-Path -LiteralPath $local) { return $local }
  return $null
}

function Ensure-TbccDependencies {
  param(
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string]$PythonCmd,
    [bool]$FullStack = $false,
    [bool]$SkipEnrichment = $false
  )
  $backendDir = Join-Path $TbccRoot "backend"
  $dashboardDir = Join-Path $TbccRoot "dashboard"
  $aofForumDir = Join-Path (Split-Path $TbccRoot -Parent) "aof-forum"
  $servicesDir = Join-Path $TbccRoot "services"

  Write-Host "[deps] Python backend (pip install -r requirements.txt)..." -ForegroundColor Yellow
  $req = Join-Path $backendDir "requirements.txt"
  if (Test-Path -LiteralPath $req) {
    Push-Location $backendDir
    cmd /c ($PythonCmd + " -m pip install -q -r requirements.txt")
    if ($LASTEXITCODE -ne 0) {
      Write-Host "  Backend pip install failed. Fix Python 3.13 / network, then re-run." -ForegroundColor Red
    } else {
      Write-Host "  Backend Python deps OK." -ForegroundColor Green
    }
    Pop-Location
  }

  function Install-NpmIfNeeded {
    param([string]$Dir, [string]$Label)
    $pkg = Join-Path $Dir "package.json"
    if (-not (Test-Path -LiteralPath $pkg)) { return }
    $nm = Join-Path $Dir "node_modules"
    if (Test-Path -LiteralPath $nm) {
      Write-Host ('  ' + $Label + ' node_modules present.') -ForegroundColor Gray
      return
    }
    Write-Host ('[deps] ' + $Label + ' (npm install, first run may take a minute)...') -ForegroundColor Yellow
    Push-Location $Dir
    cmd /c "npm install"
    if ($LASTEXITCODE -ne 0) {
      Write-Host ('  ' + $Label + ' npm install failed.') -ForegroundColor Red
    } else {
      Write-Host ('  ' + $Label + ' npm OK.') -ForegroundColor Green
    }
    Pop-Location
  }

  Install-NpmIfNeeded -Dir $dashboardDir -Label "Dashboard"
  Install-NpmIfNeeded -Dir $aofForumDir -Label "AOF Forum"

  if ($SkipEnrichment) {
    Write-Host '[deps] Skipping enrichment (-SkipEnrichment).' -ForegroundColor DarkGray
    return
  }

  $nsfwReq = Join-Path $servicesDir "NSFW_Detection_API\requirements.txt"
  if (Test-Path -LiteralPath $nsfwReq) {
    Write-Host "[deps] NSFW Detection API (pip + setuptools pin for tensorflow-hub)..." -ForegroundColor Yellow
    Push-Location (Join-Path $servicesDir "NSFW_Detection_API")
    cmd /c ($PythonCmd + " -m pip install -q -r requirements.txt")
    $pin = Join-Path $servicesDir "nsfw-detect-tbcc.txt"
    if (Test-Path -LiteralPath $pin) {
      cmd /c ($PythonCmd + ' -m pip install -q -r "' + $pin + '"')
    } else {
      cmd /c ($PythonCmd + ' -m pip install -q "setuptools>=70,<81"')
    }
    cmd /c ($PythonCmd + ' -c "import os; os.environ[''TF_USE_LEGACY_KERAS'']=''1''; from pkg_resources import parse_version; import tensorflow_hub; import tf_keras"') 2>$null
    if ($LASTEXITCODE -ne 0) {
      Write-Host "  NSFW deps check failed. Run: cd services ; .\setup-enrichment.ps1" -ForegroundColor Red
    } else {
      Write-Host "  NSFW Detection API deps OK." -ForegroundColor Green
    }
    Pop-Location
  } elseif ($FullStack) {
    Write-Host '[deps] NSFW repo not found under services\NSFW_Detection_API (see services\README.md).' -ForegroundColor DarkYellow
  }

  $lustPkg = Join-Path $servicesDir "lustpress\package.json"
  if (Test-Path -LiteralPath $lustPkg) {
    $bun = Get-BunExecutable
    $lustNm = Join-Path $servicesDir "lustpress\node_modules"
    if (-not $bun) {
      Write-Host '[deps] Lustpress: bun not on PATH. Run: cd services ; .\setup-enrichment.ps1' -ForegroundColor DarkYellow
    } elseif (-not (Test-Path -LiteralPath $lustNm)) {
      Write-Host "[deps] Lustpress (bun install)..." -ForegroundColor Yellow
      Push-Location (Join-Path $servicesDir "lustpress")
      & $bun install
      if ($LASTEXITCODE -ne 0) {
        Write-Host "  Lustpress bun install failed." -ForegroundColor Red
      } else {
        Write-Host "  Lustpress deps OK." -ForegroundColor Green
      }
      Pop-Location
    } else {
      Write-Host "  Lustpress node_modules present." -ForegroundColor Gray
    }
  } elseif ($FullStack) {
    Write-Host '[deps] Lustpress repo not found under services\lustpress (see services\README.md).' -ForegroundColor DarkYellow
  }
}

function Get-TbccEnrichmentSidecars {
  param(
    [Parameter(Mandatory = $true)][hashtable]$EnvMap,
    [Parameter(Mandatory = $true)][string]$TbccRoot,
    [Parameter(Mandatory = $true)][string]$PythonCmd
  )
  $titles = New-Object System.Collections.ArrayList
  $cmds = New-Object System.Collections.ArrayList
  $notes = New-Object System.Collections.ArrayList
  $servicesDir = Join-Path $TbccRoot "services"

  $nsfwUrl = $EnvMap["TBCC_NSFW_DETECT_URL"]
  if ((Test-LocalhostServiceUrl $nsfwUrl) -and -not (Wait-HttpOk -Uri ($nsfwUrl.TrimEnd("/") + "/") -MaxSeconds 2)) {
    $nsfwDir = $EnvMap["TBCC_NSFW_DETECT_DIR"]
    if (-not $nsfwDir) { $nsfwDir = Join-Path $servicesDir "NSFW_Detection_API" }
    if (Test-Path -LiteralPath (Join-Path $nsfwDir "requirements.txt")) {
      $launcher = Join-Path $servicesDir "run_nsfw_detect.py"
      [void]$titles.Add("TBCC-NSFW-Detect")
      [void]$cmds.Add(('cd /d "' + $servicesDir + '" & ' + $PythonCmd + ' run_nsfw_detect.py'))
      [void]$notes.Add("NSFW Detection API -> " + $nsfwUrl + " (via run_nsfw_detect.py, not port 8000)")
    } else {
      [void]$notes.Add("TBCC_NSFW_DETECT_URL is set but repo missing at: " + $nsfwDir + " (see services\README.md)")
    }
  } elseif ($nsfwUrl -and (Test-LocalhostServiceUrl $nsfwUrl) -and (Wait-HttpOk -Uri ($nsfwUrl.TrimEnd("/") + "/") -MaxSeconds 2)) {
    [void]$notes.Add("NSFW Detection API already up at " + $nsfwUrl)
  }

  $lustUrl = $EnvMap["TBCC_LUSTPRESS_URL"]
  if ((Test-LocalhostServiceUrl $lustUrl) -and -not (Wait-HttpOk -Uri ($lustUrl.TrimEnd("/") + "/") -MaxSeconds 2)) {
    $lustDir = $EnvMap["TBCC_LUSTPRESS_DIR"]
    if (-not $lustDir) { $lustDir = Join-Path $servicesDir "lustpress" }
    $pkg = Join-Path $lustDir "package.json"
    if (Test-Path -LiteralPath $pkg) {
      $bunCmd = Get-BunExecutable
      $nodeModules = Join-Path $lustDir "node_modules"
      if ($bunCmd -and -not (Test-Path -LiteralPath $nodeModules)) {
        [void]$notes.Add("Lustpress: run tbcc\services\setup-enrichment.ps1 (bun install not done yet)")
      } elseif ($bunCmd) {
        $bunQ = '"' + $bunCmd + '"'
        [void]$titles.Add("TBCC-Lustpress")
        [void]$cmds.Add(('cd /d "' + $lustDir + '" & ' + $bunQ + ' run start:dev'))
        [void]$notes.Add("Lustpress -> " + $lustUrl)
      } else {
        [void]$notes.Add("TBCC_LUSTPRESS_URL is set but bun not found. Run: cd tbcc\services ; .\setup-enrichment.ps1")
      }
    } else {
      [void]$notes.Add("TBCC_LUSTPRESS_URL is set but repo missing at: " + $lustDir + " (see services\README.md)")
    }
  } elseif ($lustUrl -and (Test-LocalhostServiceUrl $lustUrl) -and (Wait-HttpOk -Uri ($lustUrl.TrimEnd("/") + "/") -MaxSeconds 2)) {
    [void]$notes.Add("Lustpress already up at " + $lustUrl)
  }

  return @{
    Titles = [string[]]$titles.ToArray()
    Commands = [string[]]$cmds.ToArray()
    Notes = [string[]]$notes.ToArray()
  }
}

function Import-TbccErrorHubModule {
  if ($script:TbccErrorHubLoaded) { return }
  $hub = Join-Path $tbccDir 'scripts\tbcc-error-hub.ps1'
  if (-not (Test-Path -LiteralPath $hub)) {
    throw 'Missing tbcc-error-hub.ps1 - re-pull the repo or restore tbcc\scripts\'
  }
  $dot = [scriptblock]::Create(('. ' + "'" + ($hub -replace "'", "''") + "'"))
  $null = $ExecutionContext.InvokeCommand.InvokeScript(
    $dot,
    $false,
    [System.Management.Automation.Language.CommandRedirection[]]@(),
    [System.Management.Automation.ScopeType]::Script
  )
  $script:TbccErrorHubLoaded = $true
}

function Initialize-TbccErrorHubSession {
  Import-TbccErrorHubModule
  $paths = Initialize-TbccErrorHub -TbccRoot $tbccDir
  Write-Host ('  Error hub log: ' + $paths.LogPath) -ForegroundColor Gray
  return $paths
}

function Wrap-TbccServiceCommandsForErrorHub {
  param(
    [Parameter(Mandatory = $true)][string[]]$Titles,
    [Parameter(Mandatory = $true)][string[]]$Commands
  )
  Import-TbccErrorHubModule
  $wrapped = New-Object System.Collections.ArrayList
  for ($i = 0; $i -lt $Titles.Length; $i++) {
    $null = Register-TbccServiceLauncher -TbccRoot $tbccDir -ServiceName $Titles[$i] -Command $Commands[$i]
    [void]$wrapped.Add((Get-TbccServiceWrapperCmd -TbccRoot $tbccDir -ServiceName $Titles[$i]))
  }
  return [string[]]$wrapped.ToArray()
}

function Start-TbccCmdWindow {
  param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$Command,
    [int]$Cols = 100,
    [int]$Lines = 28
  )
  # mode con sets buffer/size so multiple windows are easier to arrange (classic conhost)
  $part1 = "mode con: cols=$Cols lines=$Lines"
  $part2 = [string]::Concat('title "', $Title, '"')
  $run = [string]::Concat($part1, ' & ', $part2, ' & ', $Command)
  Start-Process -FilePath $env:ComSpec -ArgumentList @("/k", $run) -WindowStyle Normal
}

function Start-TbccWtTabs {
  param(
    [Parameter(Mandatory = $true)][string[]]$Titles,
    [Parameter(Mandatory = $true)][string[]]$Commands,
    [int]$Cols = 100,
    [int]$Lines = 28
  )
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
      if (Test-Path -LiteralPath $p) { $wtExe = $p; break }
    }
  }
  if (-not $wtExe) {
    Write-Host '  Windows Terminal (wt.exe) not found - opening separate cmd windows instead.' -ForegroundColor DarkYellow
    return $false
  }
  if ($Titles.Length -ne $Commands.Length) {
    throw "Start-TbccWtTabs: Titles and Commands count must match."
  }
  # Always open a fresh WT window (-w -1). Without this, WT may append tabs to the
  # last-used window (windowingBehavior / user still closing the old stack).
  $al = New-Object System.Collections.ArrayList
  for ($i = 0; $i -lt $Titles.Length; $i++) {
    $part1 = "mode con: cols=$Cols lines=$Lines"
    $part2 = [string]::Concat('title "', $Titles[$i], '"')
    $run = [string]::Concat($part1, ' & ', $part2, ' & ', $Commands[$i])
    if ($i -gt 0) { [void]$al.Add(';') }
    if ($i -eq 0) {
      [void]$al.Add('-w')
      [void]$al.Add('-1')
    }
    [void]$al.Add('new-tab')
    [void]$al.Add('--title')
    [void]$al.Add($Titles[$i])
    [void]$al.Add('cmd')
    [void]$al.Add('/k')
    [void]$al.Add($run)
  }
  $proc = Start-Process -FilePath $wtExe -ArgumentList @($al.ToArray()) -WindowStyle Normal -PassThru
  $controlScript = Join-Path $tbccDir "scripts\tbcc-service-control.ps1"
  if (Test-Path -LiteralPath $controlScript) {
    . $controlScript
    Register-TbccWtTabHostFromLauncher -TbccRoot $tbccDir -LauncherPid $proc.Id
  } else {
    $runDir = Join-Path $tbccDir ".tbcc-run"
    if (-not (Test-Path -LiteralPath $runDir)) {
      New-Item -ItemType Directory -Path $runDir -Force | Out-Null
    }
    Set-Content -LiteralPath (Join-Path $runDir "wt-tab-host.pid") -Value $proc.Id -Encoding ascii -NoNewline
  }
  return $true
}

function Ensure-DockerDesktopRunning {
  param([int]$MaxWaitSeconds = 300)
  cmd /c "docker info" >$null 2>&1
  if ($LASTEXITCODE -eq 0) {
    Write-Host "  Docker engine already running." -ForegroundColor Gray
    return $true
  }
  $candidates = @(
    "${env:ProgramFiles}\Docker\Docker\Docker Desktop.exe",
    "${env:ProgramFiles(x86)}\Docker\Docker\Docker Desktop.exe"
  )
  $dd = $null
  foreach ($p in $candidates) {
    if (Test-Path -LiteralPath $p) { $dd = $p; break }
  }
  if (-not $dd) {
    Write-Host "  Docker Desktop executable not found. Install Docker Desktop for Windows or start the engine manually." -ForegroundColor Red
    return $false
  }
  Write-Host ('  Starting Docker Desktop (waiting for engine, up to ' + $MaxWaitSeconds + ' s)...') -ForegroundColor Yellow
  Start-Process -FilePath $dd
  $deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    cmd /c "docker info" >$null 2>&1
    if ($LASTEXITCODE -eq 0) {
      Write-Host "  Docker engine is ready." -ForegroundColor Green
      return $true
    }
  }
  Write-Host "  Timed out waiting for Docker. Open Docker Desktop manually, wait until it says ""Running"", then re-run this script." -ForegroundColor Red
  return $false
}

Write-Host "TBCC Launch" -ForegroundColor Cyan
Write-Host ('  Python: ' + $tbccPython + ' (TBCC backend / bots / Celery)') -ForegroundColor Gray
Write-Host '  Backend: http://localhost:8000 | Dashboard: http://127.0.0.1:5173 | AOF Forum: http://127.0.0.1:3001 (repo sibling ..\aof-forum)' -ForegroundColor Gray
if ($fullStack) {
  Write-Host '  Full stack: Postgres+Redis (Docker) + workers + optional enrichment (NSFW API, Lustpress)' -ForegroundColor Gray
  Write-Host '  Listening relay (Dashboard > Misc): uses TBCC-Celery + TBCC-Beat only — same -Full tabs, no separate Last.fm service.' -ForegroundColor Gray
}
Write-Host ('  Console: ' + $consoleCols + 'x' + $consoleLines + ' - use -CompactConsole / -WideConsole for window size, or -WtTabs for one Windows Terminal with tabs') -ForegroundColor Gray
Write-Host ""

if ($skipDeps) {
  Write-Host '[deps] Skipping dependency checks (-SkipDeps).' -ForegroundColor DarkYellow
} else {
  Ensure-TbccDependencies -TbccRoot $tbccDir -PythonCmd $tbccPython -FullStack $fullStack -SkipEnrichment $skipEnrichment
  Write-Host ""
}

# 0. Postgres + Redis via compose (minimal file: infra/docker-compose.infra.yml)
$infraCompose = Join-Path $tbccDir "infra\docker-compose.infra.yml"
$legacyCompose = Join-Path $tbccDir "infra\docker-compose.yml"
$composeFile = if (Test-Path $infraCompose) { $infraCompose } elseif (Test-Path $legacyCompose) { $legacyCompose } else { $null }

# Docker CLI is used for compose (postgres/redis) and/or -Full (redis check). Start Desktop if needed.
$needsDockerEngine = $fullStack -or ((-not $skipDocker) -and $null -ne $composeFile)
if ($needsDockerEngine) {
  Write-Host "[0a] Docker: ensure engine is running..." -ForegroundColor Yellow
  $null = Ensure-DockerDesktopRunning
  Write-Host ""
}

if ($skipDocker) {
  Write-Host '[0] Skipping Docker (-SkipDocker). Ensure Postgres :5432 and Redis :6379 are up if your .env needs them.' -ForegroundColor DarkYellow
} elseif ($composeFile) {
  Write-Host "[0] Docker: postgres + redis ($([IO.Path]::GetFileName($composeFile)))..." -ForegroundColor Yellow
  Write-Host '  FIRST RUN: image download can take 5-20+ minutes (Postgres is large). Let it finish.' -ForegroundColor Yellow
  Write-Host "  Do NOT press Ctrl+C here - the script will not start backend/dashboard until this completes." -ForegroundColor Yellow
  Push-Location (Join-Path $tbccDir "infra")
  try {
    $composeName = [IO.Path]::GetFileName($composeFile)
    $envFile = Join-Path $tbccDir ".env"
    # Use cmd /c so Docker writing status to stderr does not become PowerShell "NativeCommandError" (red text).
    if ($composeName -eq "docker-compose.infra.yml") {
      cmd /c "docker compose -f docker-compose.infra.yml up -d postgres redis"
    } elseif (Test-Path $envFile) {
      $ef = (Resolve-Path $envFile).Path
      cmd /c ('docker compose --env-file "' + $ef + '" -f "' + $composeName + '" up -d postgres redis')
    } else {
      cmd /c ('docker compose -f "' + $composeName + '" up -d postgres redis')
    }
    if ($LASTEXITCODE -ne 0) {
      Write-Host ('  docker compose exited with code ' + $LASTEXITCODE + ' (check Docker Desktop / disk space).') -ForegroundColor Red
    }
  } finally {
    Pop-Location
  }
  Start-Sleep -Seconds 3
  Write-Host "  Postgres: localhost:5432  Redis: localhost:6379" -ForegroundColor Green
} else {
  Write-Host "[0] No infra/docker-compose*.yml - ensure Postgres/Redis yourself." -ForegroundColor DarkYellow
}

$backendDir = Join-Path $tbccDir "backend"
$dashboardDir = Join-Path $tbccDir "dashboard"
$aofForumDir = Join-Path (Split-Path $tbccDir -Parent) "aof-forum"
$hasAofForum = Test-Path (Join-Path $aofForumDir "package.json")

# 0.5 Alembic — Postgres: apply migrations before API starts (SQLite gets many tables via create_all + patches).
#    Includes newer tables/columns (e.g. promo_affiliate_links for Misc promo picker / bulk JSON import).
if (-not $skipMigrations) {
  Write-Host "[0.5] Database migrations: alembic upgrade head..." -ForegroundColor Yellow
  Push-Location $backendDir
  try {
    cmd /c ($tbccPython + ' -m alembic upgrade head')
    if ($LASTEXITCODE -ne 0) {
      Write-Host "  Migrations failed. Check tbcc\.env DATABASE_URL and that Postgres is running." -ForegroundColor Red
      Write-Host ('  Manual fix: cd "' + $backendDir + '" ; ' + $tbccPython + ' -m alembic upgrade head') -ForegroundColor Yellow
    } else {
      Write-Host "  OK: schema is up to date." -ForegroundColor Green
    }
  } finally {
    Pop-Location
  }
} else {
  Write-Host '[0.5] Skipping migrations (-SkipMigrations).' -ForegroundColor DarkYellow
  Write-Host ('      If Postgres lacks newer tables, run: cd backend ; ' + $tbccPython + ' -m alembic upgrade head') -ForegroundColor DarkYellow
  Write-Host '      (Backend startup also CREATE TABLE IF NOT EXISTS promo_affiliate_links on Postgres as a safety net.)' -ForegroundColor DarkGray
}

# Clear stale uvicorn reload children before binding :8000 (hands-off; same as dashboard Fix button).
$cleanupOrphans = Join-Path $tbccDir "scripts\tbcc-cleanup-orphans.ps1"
if (Test-Path -LiteralPath $cleanupOrphans) {
  try { & powershell -NoProfile -ExecutionPolicy Bypass -File $cleanupOrphans 2>$null | Out-Null } catch {}
}

# Service commands (cmd.exe: use one & between parts - avoids PS7 tokenizing && in scripts)
$uvicornReload = if ($noReload) { '' } else { ' --reload --reload-exclude scripts --reload-delay 1' }
$cmdBackend = 'cd /d "' + $backendDir + '" & ' + $tbccPython + ' -m uvicorn app.main:app --host 127.0.0.1 --port 8000' + $uvicornReload
$cmdDashboard = 'cd /d "' + $dashboardDir + '" & npm run dev'
$cmdAofForum = if ($hasAofForum) { 'cd /d "' + $aofForumDir + '" & npm run dev' } else { '' }
$cmdCelery = 'cd /d "' + $backendDir + '" & ' + $tbccPython + ' -m celery -A app.workers.celery_app worker -l info -P solo -Q celery,post,scrape,subscription,telegram'
$cmdBeat = 'cd /d "' + $backendDir + '" & ' + $tbccPython + ' -m celery -A app.workers.celery_app beat -l info'
$cmdPay = 'cd /d "' + $backendDir + '" & ' + $tbccPython + ' -m bots.payment_bot'
$cmdSecretary = 'cd /d "' + $backendDir + '" & ' + $tbccPython + ' -m bots.secretary_bot'
$cmdLoot = 'cd /d "' + $backendDir + '" & ' + $tbccPython + ' -m bots.loot_bot'
$cmdLlmChat = 'cd /d "' + $backendDir + '" & ' + $tbccPython + ' -m bots.llm_chat_bot'

$dotEnv = Read-TbccDotEnv -Path (Join-Path $tbccDir ".env")
$enrichment = @{ Titles = @(); Commands = @(); Notes = @() }
if (-not $skipEnrichment) {
  $enrichment = Get-TbccEnrichmentSidecars -EnvMap $dotEnv -TbccRoot $tbccDir -PythonCmd $tbccPython
  foreach ($n in $enrichment.Notes) {
    if ($n -match "missing|not on PATH") {
      Write-Host ('  [Enrichment] ' + $n) -ForegroundColor DarkYellow
    } elseif ($n) {
      Write-Host ('  [Enrichment] ' + $n) -ForegroundColor Gray
    }
  }
}

$redisOk = $false
if ($fullStack) {
  Start-Sleep -Seconds 1
  Write-Host "[Full] Checking Redis on :6379..." -ForegroundColor Yellow
  $r = docker ps -q -f "ancestor=redis" 2>$null
  if ($r) { $redisOk = $true }
  if (-not $redisOk) {
    try {
      $null = docker run -d -p 6379:6379 redis 2>&1
      if ($LASTEXITCODE -eq 0) { $redisOk = $true }
    } catch {}
  }
  if (-not $redisOk) {
    $r2 = docker ps --format "{{.Ports}}" 2>$null | Select-String "6379"
    if ($r2) { $redisOk = $true }
  }
  if ($redisOk) {
    Write-Host '  Redis reachable (container or port 6379).' -ForegroundColor Green
  } else {
    Write-Host "  Redis not detected - Celery/payment bot may fail. Run: cd infra; docker compose up -d redis" -ForegroundColor Red
  }
}

$wtLaunched = $false
$errorHubReady = $false
if ($useErrorHub) {
  Write-Host '[hub] TBCC Error Hub - unified error/warn log (TBCC-Errors tab with -WtTabs).' -ForegroundColor Cyan
  $null = Initialize-TbccErrorHubSession
  $errorHubReady = $true
}

if ($wtTabs) {
  $controlScript = Join-Path $tbccDir "scripts\tbcc-service-control.ps1"
  if (Test-Path -LiteralPath $controlScript) {
    . $controlScript
    if (-not $skipPriorStackStop) {
      Write-Host '[stop] Closing prior TBCC stack (services + Windows Terminal tabs)...' -ForegroundColor Yellow
      $gone = Stop-TbccPriorStackWindows -TbccRoot $tbccDir -FullStack:$fullStack -ExcludeProcessIds @($PID) -Wait -MaxWaitSeconds 60
      if ($gone) {
        Write-Host '[stop] Prior stack fully stopped — starting fresh WT window.' -ForegroundColor Green
      } else {
        Write-Host '[stop] WARNING: Prior stack may still be up (extra tabs or ports in use). Close old TBCC Windows Terminal windows manually if needed.' -ForegroundColor Red
      }
    } else {
      Write-Host '[stop] Skipped (-SkipPriorStackStop; prior stop already done by cold-start launcher).' -ForegroundColor Gray
    }
  }
  $titles = @('TBCC-Backend', 'TBCC-Dashboard')
  $cmds = @($cmdBackend, $cmdDashboard)
  if ($hasAofForum) {
    $titles += 'AOF-Forum'
    $cmds += $cmdAofForum
  }
  if ($fullStack -and $redisOk) {
    $titles += 'TBCC-Celery', 'TBCC-Beat', 'TBCC-PaymentBot', 'TBCC-SecretaryBot', 'TBCC-LootBot'
    $cmds += $cmdCelery, $cmdBeat, $cmdPay, $cmdSecretary, $cmdLoot
  } elseif ($fullStack -and -not $redisOk) {
    $titles += 'TBCC-LootBot'
    $cmds += $cmdLoot
    Write-Host '  (-WtTabs) Redis unavailable — Backend + Dashboard + Loot overseer (no Celery/Beat/Payment/Secretary).' -ForegroundColor DarkYellow
  }
  if ($enrichment.Titles.Length -gt 0) {
    $titles += $enrichment.Titles
    $cmds += $enrichment.Commands
  }
  if ($llmChat) {
    $titles += 'TBCC-LlmChatBot'
    $cmds += $cmdLlmChat
  }
  if ($useErrorHub) {
    Import-TbccErrorHubModule
    $cmds = Wrap-TbccServiceCommandsForErrorHub -Titles $titles -Commands $cmds
    $titles = @('TBCC-Errors') + $titles
    $cmds = @(Get-TbccErrorMonitorCmd -TbccRoot $tbccDir) + $cmds
  }
  $wtLaunched = Start-TbccWtTabs -Titles $titles -Commands $cmds -Cols $consoleCols -Lines $consoleLines
}

function Start-TbccServiceWindow {
  param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$Command
  )
  $run = $Command
  if ($useErrorHub) {
    Import-TbccErrorHubModule
    $null = Register-TbccServiceLauncher -TbccRoot $tbccDir -ServiceName $Title -Command $Command
    $run = Get-TbccServiceWrapperCmd -TbccRoot $tbccDir -ServiceName $Title
  }
  Start-TbccCmdWindow -Title $Title -Command $run -Cols $consoleCols -Lines $consoleLines
}

# 1. Backend (port 8000) — and 2. Dashboard when not using wt tabs
if (-not $wtLaunched) {
  if ($useErrorHub -and -not $errorHubReady) {
    $null = Initialize-TbccErrorHubSession
    $errorHubReady = $true
  }
  if ($useErrorHub) {
    Write-Host '[0] Starting TBCC-Errors monitor (new window)...' -ForegroundColor Yellow
    Import-TbccErrorHubModule
    Start-TbccCmdWindow -Title "TBCC-Errors" -Command (Get-TbccErrorMonitorCmd -TbccRoot $tbccDir) -Cols $consoleCols -Lines $consoleLines
  }
  $n = if ($hasAofForum) { 3 } else { 2 }
  Write-Host ('[1/' + $n + '] Starting backend (new window)...') -ForegroundColor Yellow
  Start-TbccServiceWindow -Title "TBCC-Backend" -Command $cmdBackend
} else {
  if ($hasAofForum) {
    Write-Host '[1/3+] Started backend, dashboard, AOF Forum in Windows Terminal (tabs).' -ForegroundColor Yellow
  } else {
    Write-Host '[1/2+] Started backend + dashboard in Windows Terminal (tabs).' -ForegroundColor Yellow
  }
}

Write-Host '  Waiting for API (http://127.0.0.1:8000/health) ...' -ForegroundColor Gray
Start-Sleep -Seconds 3
$backendUp = $false
for ($i = 0; $i -lt 35; $i++) {
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    if ($r.StatusCode -eq 200) {
      $backendUp = $true
      break
    }
  } catch {
    # Backend still starting or failed — keep trying
  }
  Start-Sleep -Seconds 2
}
if ($backendUp) {
  Write-Host "  Backend responded OK - safe to use the dashboard." -ForegroundColor Green
} else {
  Write-Host "" 
  Write-Host "  *** BACKEND NOT REACHABLE ON PORT 8000 ***" -ForegroundColor Red
  Write-Host '  Open the window titled TBCC-Backend and read the error (Python traceback, missing module, DB).' -ForegroundColor Yellow
  Write-Host ('  Try: cd "' + $backendDir + '" ; ' + $tbccPython + ' -m pip install -r requirements.txt ; ' + $tbccPython + ' -m uvicorn app.main:app --host 127.0.0.1 --port 8000') -ForegroundColor Yellow
  Write-Host "  Test in browser: http://127.0.0.1:8000/docs" -ForegroundColor Yellow
  Write-Host ""
}

# 2. Dashboard (port 5173)
if (-not $wtLaunched) {
  $n = if ($hasAofForum) { 3 } else { 2 }
  Write-Host ('[2/' + $n + '] Starting dashboard (new window)...') -ForegroundColor Yellow
  Start-TbccServiceWindow -Title "TBCC-Dashboard" -Command $cmdDashboard
} else {
  Write-Host '[2/3+] Dashboard tab already running (Windows Terminal).' -ForegroundColor Gray
}

# 2b. AOF Forum — Next.js front (port 3001); sibling folder ..\aof-forum
if ($hasAofForum -and -not $wtLaunched) {
  Write-Host '[3/3] Starting AOF Forum — Next.js (new window)...' -ForegroundColor Yellow
  Start-TbccServiceWindow -Title "AOF-Forum" -Command $cmdAofForum
} elseif (-not $hasAofForum) {
  Write-Host '  (No ..\aof-forum\package.json — skipping AOF Forum dev server.)' -ForegroundColor DarkGray
}

if ($fullStack) {
  if ($wtLaunched) {
    Write-Host '[3/8]–[8/8] Full stack already in Windows Terminal tabs (or Backend+Dashboard+Loot if Redis was down).' -ForegroundColor Gray
  } elseif ($redisOk) {
    Start-Sleep -Seconds 1
    Write-Host '[4/8] Starting Celery worker (new window)...' -ForegroundColor Yellow
    Start-TbccServiceWindow -Title "TBCC-Celery" -Command $cmdCelery
    Write-Host "  Celery worker started." -ForegroundColor Green
    Write-Host '[5/8] Starting Celery Beat (new window)...' -ForegroundColor Yellow
    Start-TbccServiceWindow -Title "TBCC-Beat" -Command $cmdBeat
    Write-Host "  Celery Beat started." -ForegroundColor Green
    Write-Host '[6/8] Starting payment bot (new window)...' -ForegroundColor Yellow
    Start-TbccServiceWindow -Title "TBCC-PaymentBot" -Command $cmdPay
    Write-Host "  Payment bot started." -ForegroundColor Green
    Write-Host '[7/8] Starting secretary bot (FAQ / Business drafts) (new window)...' -ForegroundColor Yellow
    Start-TbccServiceWindow -Title "TBCC-SecretaryBot" -Command $cmdSecretary
    Write-Host "  Secretary bot started." -ForegroundColor Green
    Write-Host '[8/8] Starting loot overseer bot (new window)...' -ForegroundColor Yellow
    Start-TbccServiceWindow -Title "TBCC-LootBot" -Command $cmdLoot
    Write-Host "  Loot overseer bot started." -ForegroundColor Green
    foreach ($i in 0..($enrichment.Titles.Length - 1)) {
      $t = $enrichment.Titles[$i]
      $c = $enrichment.Commands[$i]
      Write-Host ('Starting ' + $t + ' (enrichment sidecar)...') -ForegroundColor Yellow
      Start-TbccServiceWindow -Title $t -Command $c
      Write-Host ('  ' + $t + ' started.') -ForegroundColor Green
    }
  } elseif (-not $redisOk) {
    Write-Host '[3/4] Redis down — starting loot overseer only (needs API, not Redis)...' -ForegroundColor Yellow
    Start-TbccServiceWindow -Title "TBCC-LootBot" -Command $cmdLoot
    Write-Host "  Loot overseer bot started." -ForegroundColor Green
  }
  if ($llmChat -and -not $wtLaunched) {
    Write-Host 'Starting LLM chat bot (new window)...' -ForegroundColor Yellow
    Start-TbccServiceWindow -Title "TBCC-LlmChatBot" -Command $cmdLlmChat
    Write-Host "  LLM chat bot started." -ForegroundColor Green
  }
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
if ($wtLaunched) {
  if ($useErrorHub) {
    Write-Host '  Windows Terminal: first tab TBCC-Errors = unified log; other tabs = live service output.' -ForegroundColor Gray
    Write-Host '  Log file: tbcc\.tbcc-run\error-hub.log (truncated lines end with ....)' -ForegroundColor Gray
  } else {
    Write-Host '  Services run in one Windows Terminal window (tabs TBCC-*). Switch tabs at the top.' -ForegroundColor Gray
  }
} else {
  Write-Host '  You should see separate CMD windows titled TBCC-* - check them for errors.' -ForegroundColor Gray
}
Write-Host "  If the dashboard cannot reach the backend, wait ~10s then refresh. Check DB, .env, and Python deps." -ForegroundColor Gray
if ($fullStack -and $redisOk) {
  Write-Host '  Misc > Listening relay: TBCC-Beat + TBCC-Celery tabs must stay open.' -ForegroundColor Gray
  Write-Host '  Auto-tag enrich (Lustpress + NSFW + LLM fallback): clone sidecars to tbcc\services\ if .env URLs are localhost (services\README.md).' -ForegroundColor Gray
}
if ($fullStack -and -not $redisOk) {
  Write-Host '  Misc > Listening relay: Celery/Beat were NOT started (Redis missing). Fix Redis, then re-run -Full or start worker+beat manually.' -ForegroundColor DarkYellow
}
if (-not $fullStack) {
  Write-Host 'For posting + listening relay polls: run with -Full (Redis + Celery + Beat). Example:  .\start.ps1 -Full -WtTabs' -ForegroundColor Gray
  Write-Host 'Or start Redis + Celery worker + Celery beat manually (see README).' -ForegroundColor Gray
}
Write-Host ""
if (-not $noOpenBrowser) {
  Write-Host 'Opening dashboard (http://127.0.0.1:5173) in Brave if installed, otherwise your default browser...' -ForegroundColor Yellow
  $dashReady = Wait-HttpOk -Uri "http://127.0.0.1:5173/"
  if (-not $dashReady) {
    Write-Host '  Dashboard not responding yet — opening URL anyway; refresh if the page is blank.' -ForegroundColor DarkYellow
  }
  Open-UrlInPreferredBrowser -Url "http://127.0.0.1:5173/"
  if ($hasAofForum) {
    Write-Host 'Opening AOF Forum (http://127.0.0.1:3001)...' -ForegroundColor Yellow
    Start-Sleep -Seconds 2
    $forumReady = Wait-HttpOk -Uri "http://127.0.0.1:3001/" -MaxSeconds 45
    if (-not $forumReady) {
      Write-Host '  AOF Forum not responding yet (npm install / first compile?) — opened URL anyway; refresh if blank.' -ForegroundColor DarkYellow
    }
    Open-UrlInPreferredBrowser -Url "http://127.0.0.1:3001/"
  }
  if ($openDocsToo) {
    Start-Sleep -Seconds 1
    Open-UrlInPreferredBrowser -Url "http://127.0.0.1:8000/docs"
  }
} else {
  Write-Host 'Skipping browser (-NoOpen).' -ForegroundColor Gray
}
Write-Host '  URLs: http://127.0.0.1:5173  |  http://127.0.0.1:3001  |  http://127.0.0.1:8000/docs  (add -Open for /docs; -NoOpen skips browser)' -ForegroundColor Gray
if ($wtLaunched) {
  Write-Host ""
  Write-Host '  Launcher done - service tabs are in Windows Terminal (TBCC-Errors tab = unified log).' -ForegroundColor Green
  Write-Host '  This window stays open so you can scroll Docker/migration output above.' -ForegroundColor Gray
}
