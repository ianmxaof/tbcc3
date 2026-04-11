# TBCC Launch Script (Windows PowerShell 5.1+ and pwsh 7+). Cmd lines use single & between commands (cmd.exe).
#   .\start.ps1              — backend + dashboard; opens http://127.0.0.1:5173 in Brave if installed, else default browser
#   .\start.ps1 -NoOpen      — do not open a browser
#   .\start.ps1 -Open        — also open http://127.0.0.1:8000/docs (Swagger) in the same browser
#   .\start.ps1 -Full        — backend + dashboard + Redis + Celery + Beat + payment bot
#   .\start.ps1 -SkipDocker     — skip Postgres/Redis step (use when Docker DBs already running)
#   .\start.ps1 -SkipMigrations — skip alembic upgrade (rare; only if you manage schema yourself)
#
# Console layout (many windows are easier if smaller, or use one Terminal with tabs):
#   .\start.ps1 -CompactConsole  — smaller cmd windows (88×24 buffer) so they tile more easily
#   .\start.ps1 -WideConsole     — larger windows (140×40)
#   .\start.ps1 -WtTabs          — one Windows Terminal window, one tab per service (needs wt.exe / Windows Terminal)
#   .\start.ps1 -WtTabs -Full    — all five workers (backend, dashboard, celery, beat, payment) as tabs
#
# When Docker is needed, the script starts Docker Desktop if the engine is not up yet (Windows).
# New windows use cmd.exe /k so they show reliably when run from Cursor / VS Code / ISE.

$ErrorActionPreference = "Continue"
$tbccDir = $PSScriptRoot
$fullStack = $args -contains "-Full"
$skipDocker = $args -contains "-SkipDocker"
$skipMigrations = $args -contains "-SkipMigrations"
$noOpenBrowser = $args -contains "-NoOpen"
$openDocsToo = $args -contains "-Open"
$wtTabs = ($args -contains "-WtTabs") -or ($args -contains "-WindowsTerminalTabs")
$compactConsole = $args -contains "-CompactConsole"
$wideConsole = $args -contains "-WideConsole"

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
  $al = New-Object System.Collections.ArrayList
  for ($i = 0; $i -lt $Titles.Length; $i++) {
    $part1 = "mode con: cols=$Cols lines=$Lines"
    $part2 = [string]::Concat('title "', $Titles[$i], '"')
    $run = [string]::Concat($part1, ' & ', $part2, ' & ', $Commands[$i])
    if ($i -gt 0) { [void]$al.Add(';') }
    [void]$al.Add('new-tab')
    [void]$al.Add('--title')
    [void]$al.Add($Titles[$i])
    [void]$al.Add('cmd')
    [void]$al.Add('/k')
    [void]$al.Add($run)
  }
  Start-Process -FilePath $wtExe -ArgumentList @($al.ToArray()) -WindowStyle Normal
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
Write-Host '  Backend:  http://localhost:8000 | Dashboard: http://127.0.0.1:5173' -ForegroundColor Gray
if ($fullStack) {
  Write-Host '  Full stack: Postgres+Redis (Docker) + 5 processes (Backend, Dashboard, Celery, Beat, Payment bot)' -ForegroundColor Gray
}
Write-Host ('  Console: ' + $consoleCols + 'x' + $consoleLines + ' - use -CompactConsole / -WideConsole for window size, or -WtTabs for one Windows Terminal with tabs') -ForegroundColor Gray
Write-Host ""

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

# 0.5 Alembic — Postgres does not auto-create tables (SQLite does in app startup). Required or /pools /sources return 500.
if (-not $skipMigrations) {
  Write-Host "[0.5] Database migrations: alembic upgrade head..." -ForegroundColor Yellow
  Push-Location $backendDir
  try {
    cmd /c "python -m alembic upgrade head"
    if ($LASTEXITCODE -ne 0) {
      Write-Host "  Migrations failed. Check tbcc\.env DATABASE_URL and that Postgres is running." -ForegroundColor Red
      Write-Host "  Manual fix: cd `"$backendDir`" ; python -m alembic upgrade head" -ForegroundColor Yellow
    } else {
      Write-Host "  OK: schema is up to date." -ForegroundColor Green
    }
  } finally {
    Pop-Location
  }
} else {
  Write-Host '[0.5] Skipping migrations (-SkipMigrations).' -ForegroundColor DarkYellow
}

# Service commands (cmd.exe: use one & between parts - avoids PS7 tokenizing && in scripts)
$cmdBackend = 'cd /d "' + $backendDir + '" & python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-exclude scripts --reload-delay 1'
$cmdDashboard = 'cd /d "' + $dashboardDir + '" & npm run dev'
$cmdCelery = 'cd /d "' + $backendDir + '" & python -m celery -A app.workers.celery_app worker -l info -P solo -Q celery,post,scrape,subscription'
$cmdBeat = 'cd /d "' + $backendDir + '" & python -m celery -A app.workers.celery_app beat -l info'
$cmdPay = 'cd /d "' + $backendDir + '" & python -m bots.payment_bot'

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
if ($wtTabs) {
  $titles = @('TBCC-Backend', 'TBCC-Dashboard')
  $cmds = @($cmdBackend, $cmdDashboard)
  if ($fullStack -and $redisOk) {
    $titles += 'TBCC-Celery', 'TBCC-Beat', 'TBCC-PaymentBot'
    $cmds += $cmdCelery, $cmdBeat, $cmdPay
  } elseif ($fullStack -and -not $redisOk) {
    Write-Host '  (-WtTabs) Redis unavailable - only Backend + Dashboard tabs (no Celery/Beat/Payment).' -ForegroundColor DarkYellow
  }
  $wtLaunched = Start-TbccWtTabs -Titles $titles -Commands $cmds -Cols $consoleCols -Lines $consoleLines
}

# 1. Backend (port 8000) — and 2. Dashboard when not using wt tabs
if (-not $wtLaunched) {
  Write-Host '[1/2] Starting backend (new window)...' -ForegroundColor Yellow
  Start-TbccCmdWindow -Title "TBCC-Backend" -Command $cmdBackend -Cols $consoleCols -Lines $consoleLines
} else {
  Write-Host '[1/2] Started backend + dashboard in Windows Terminal (tabs).' -ForegroundColor Yellow
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
  Write-Host "  Try in a terminal: cd `"$backendDir`" ; pip install -r requirements.txt ; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000" -ForegroundColor Yellow
  Write-Host "  Test in browser: http://127.0.0.1:8000/docs" -ForegroundColor Yellow
  Write-Host ""
}

# 2. Dashboard (port 5173)
if (-not $wtLaunched) {
  Write-Host '[2/2] Starting dashboard (new window)...' -ForegroundColor Yellow
  Start-TbccCmdWindow -Title "TBCC-Dashboard" -Command $cmdDashboard -Cols $consoleCols -Lines $consoleLines
} else {
  Write-Host '[2/2] Dashboard tab already running (Windows Terminal).' -ForegroundColor Gray
}

if ($fullStack) {
  if ($wtLaunched) {
    Write-Host '[3/6]–[6/6] Full stack already in Terminal tabs (or only Backend+Dashboard if Redis was down).' -ForegroundColor Gray
  } elseif ($redisOk) {
    Start-Sleep -Seconds 1
    Write-Host '[4/6] Starting Celery worker (new window)...' -ForegroundColor Yellow
    Start-TbccCmdWindow -Title "TBCC-Celery" -Command $cmdCelery -Cols $consoleCols -Lines $consoleLines
    Write-Host "  Celery worker started." -ForegroundColor Green
    Write-Host '[5/6] Starting Celery Beat (new window)...' -ForegroundColor Yellow
    Start-TbccCmdWindow -Title "TBCC-Beat" -Command $cmdBeat -Cols $consoleCols -Lines $consoleLines
    Write-Host "  Celery Beat started." -ForegroundColor Green
    Write-Host '[6/6] Starting payment bot (new window)...' -ForegroundColor Yellow
    Start-TbccCmdWindow -Title "TBCC-PaymentBot" -Command $cmdPay -Cols $consoleCols -Lines $consoleLines
    Write-Host "  Payment bot started." -ForegroundColor Green
  }
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
if ($wtLaunched) {
  Write-Host '  Services run in one Windows Terminal window (tabs TBCC-*). Switch tabs at the top.' -ForegroundColor Gray
} else {
  Write-Host '  You should see separate CMD windows titled TBCC-* - check them for errors.' -ForegroundColor Gray
}
Write-Host "  If the dashboard cannot reach the backend, wait ~10s then refresh. Check DB, .env, and Python deps." -ForegroundColor Gray
if (-not $fullStack) {
  Write-Host 'For posting (Post now), run with -Full:  .\start.ps1 -Full' -ForegroundColor Gray
  Write-Host 'Or start Redis + Celery manually (see README).' -ForegroundColor Gray
}
Write-Host ""
if (-not $noOpenBrowser) {
  Write-Host 'Opening dashboard (http://127.0.0.1:5173) in Brave if installed, otherwise your default browser...' -ForegroundColor Yellow
  $dashReady = Wait-HttpOk -Uri "http://127.0.0.1:5173/"
  if (-not $dashReady) {
    Write-Host '  Dashboard not responding yet — opening URL anyway; refresh if the page is blank.' -ForegroundColor DarkYellow
  }
  Open-UrlInPreferredBrowser -Url "http://127.0.0.1:5173/"
  if ($openDocsToo) {
    Start-Sleep -Seconds 1
    Open-UrlInPreferredBrowser -Url "http://127.0.0.1:8000/docs"
  }
} else {
  Write-Host 'Skipping browser (-NoOpen).' -ForegroundColor Gray
}
Write-Host '  URLs: http://127.0.0.1:5173  |  http://127.0.0.1:8000/docs  (add -Open to auto-open /docs too; -NoOpen skips all browser opens)' -ForegroundColor Gray
