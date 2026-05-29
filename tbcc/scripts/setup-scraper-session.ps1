# First-time (or reset) Telethon login for TBCC channel scraper + optional test scrape.
#
# Uses scraper.session in tbcc/backend (NOT admin.session).
# The numeric argument is SOURCE ID (Automation -> Ingest table "ID" column), NOT pool id.
#
# Usage (run in a normal PowerShell window - not the Celery service tab):
#   cd c:\Powercore-repo-main\telegram_bot2\tbcc
#   .\scripts\setup-scraper-session.ps1
#   .\scripts\setup-scraper-session.ps1 -SourceId 1
#   .\scripts\setup-scraper-session.ps1 -SourceId 1 -ResetSession
#   .\scripts\setup-scraper-session.ps1 -SourceId 1 -StopStack -RestartStack
#
param(
  [int]$SourceId = 0,
  [switch]$ResetSession,
  [switch]$StopStack = $true,
  [switch]$RestartStack
)

$ErrorActionPreference = "Stop"
$tbccDir = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $tbccDir "backend"
$envFile = Join-Path $tbccDir ".env"
$sessionFile = Join-Path $backendDir "scraper.session"
$controlScript = Join-Path $PSScriptRoot "tbcc-service-control.ps1"

function Write-Step([string]$Text) {
  Write-Host ""
  Write-Host $Text -ForegroundColor Cyan
}

function Get-TbccPythonCmd {
  try {
    & py -3.13 -c "import sys" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { return "py -3.13" }
  } catch {}
  $py313 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"
  if (Test-Path -LiteralPath $py313) { return "`"$py313`"" }
  return "python"
}

function Invoke-TbccPython([string]$Code) {
  $py = Get-TbccPythonCmd
  $prev = Get-Location
  try {
    Set-Location -LiteralPath $backendDir
    $out = Invoke-Expression "$py -c $([char]34)$Code$([char]34)" 2>&1
    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
      throw ($out | Out-String)
    }
    return $out
  } finally {
    Set-Location -LiteralPath $prev
  }
}

Write-Host "TBCC scraper session setup" -ForegroundColor Green
Write-Host "  tbcc dir:     $tbccDir"
Write-Host "  session file: $sessionFile"
Write-Host ""
Write-Host "  SOURCE ID  = row in Automation -> Ingest (column ID). Script argument." -ForegroundColor Yellow
Write-Host "  POOL ID    = where media lands (column Pool). Already on the source row." -ForegroundColor Yellow
Write-Host "  PHONE      = entered interactively when Telethon asks (e.g. +15551234567)." -ForegroundColor Yellow

if (-not (Test-Path -LiteralPath $backendDir)) {
  Write-Host "Missing backend dir: $backendDir" -ForegroundColor Red
  exit 1
}
if (-not (Test-Path -LiteralPath $envFile)) {
  Write-Host "Missing tbcc/.env (need API_ID and API_HASH)." -ForegroundColor Red
  exit 1
}

Write-Step "[1/5] Checking API_ID / API_HASH in tbcc/.env..."
$envCheck = Invoke-TbccPython @"
from pathlib import Path
from dotenv import load_dotenv
import os
load_dotenv(Path(r'$tbccDir') / '.env')
aid = (os.getenv('API_ID') or '').strip()
ah = (os.getenv('API_HASH') or '').strip()
if not aid or not ah:
    raise SystemExit('API_ID and API_HASH must be set in tbcc/.env')
print('ok')
"@
if ($envCheck -notmatch 'ok') {
  Write-Host $envCheck -ForegroundColor Red
  exit 1
}
Write-Host "  API credentials present." -ForegroundColor Green

Write-Step "[2/5] Loading Telegram sources from database..."
$listJson = Invoke-TbccPython @"
import json
from pathlib import Path
from dotenv import load_dotenv
import os
load_dotenv(Path(r'$tbccDir') / '.env')
from app.database.session import SessionLocal
from app.models.source import Source
db = SessionLocal()
rows = db.query(Source).order_by(Source.id).all()
out = []
for s in rows:
    out.append({
        'id': s.id,
        'name': s.name or '',
        'identifier': s.identifier or '',
        'pool_id': s.pool_id,
        'active': bool(s.active),
        'source_type': s.source_type or '',
        'media_types': getattr(s, 'media_types', 'both') or 'both',
        'max_messages_per_run': getattr(s, 'max_messages_per_run', 50) or 50,
    })
db.close()
print(json.dumps(out))
"@

$sources = @()
try {
  $sources = @($listJson | ConvertFrom-Json)
} catch {
  Write-Host "Could not parse sources: $listJson" -ForegroundColor Red
  exit 1
}

if (-not $sources -or $sources.Count -eq 0) {
  Write-Host "No sources in database. Add one in Automation -> Ingest first." -ForegroundColor Red
  exit 1
}

Write-Host ("  {0,-4} {1,-22} {2,-20} {3,-6} {4,-8} {5}" -f "ID", "Name", "Channel", "Pool", "Active", "Type")
foreach ($s in $sources) {
  $active = if ($s.active) { "yes" } else { "no" }
  Write-Host ("  {0,-4} {1,-22} {2,-20} {3,-6} {4,-8} {5}" -f $s.id, $s.name, $s.identifier, $s.pool_id, $active, $s.source_type)
}

$telegramSources = @($sources | Where-Object { ($_.source_type -eq "telegram_channel") -and $_.active })
if ($telegramSources.Count -eq 0) {
  Write-Host "No active telegram_channel sources. Enable Active on a Telegram source first." -ForegroundColor Red
  exit 1
}

if ($SourceId -le 0) {
  if ($telegramSources.Count -eq 1) {
    $SourceId = [int]$telegramSources[0].id
    Write-Host ""
    Write-Host "  Auto-selected source ID $SourceId (only active Telegram source)." -ForegroundColor Green
  } else {
    Write-Host ""
    $pick = Read-Host "Enter SOURCE ID to scrape (ID column, not Pool)"
    if (-not [int]::TryParse($pick, [ref]$SourceId) -or $SourceId -le 0) {
      Write-Host "Invalid source id." -ForegroundColor Red
      exit 1
    }
  }
}

$chosen = $sources | Where-Object { [int]$_.id -eq $SourceId } | Select-Object -First 1
if (-not $chosen) {
  Write-Host "Source ID $SourceId not found." -ForegroundColor Red
  exit 1
}
if ($chosen.source_type -ne "telegram_channel") {
  Write-Host "Source $SourceId is type '$($chosen.source_type)' - only telegram_channel can be scraped." -ForegroundColor Red
  exit 1
}
if (-not $chosen.active) {
  Write-Host "Source $SourceId is inactive. Enable Active in the dashboard or pick another id." -ForegroundColor Red
  exit 1
}

Write-Host ""
Write-Host "  Will scrape source ID $($chosen.id) -> pool ID $($chosen.pool_id) ($($chosen.name))" -ForegroundColor Green

if ($StopStack) {
  Write-Step "[3/5] Stopping Celery / scraper processes (avoid session lock)..."
  $killed = @()
  if (Test-Path -LiteralPath $controlScript) {
    . $controlScript
    $killed += @(Stop-TbccProcessesByCommandMatch -Pattern "celery.*app\.workers\.celery_app")
    $killed += @(Stop-TbccProcessesByCommandMatch -Pattern "run_scrape_once\.py")
    $killed += @(Stop-TbccProcessesByCommandMatch -Pattern "scraper_worker\.run_scrape")
  } else {
    $killed += @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object { $_.CommandLine -match "celery|run_scrape_once" } |
      ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId })
  }
  $killed = @($killed | Select-Object -Unique)
  if ($killed.Count -gt 0) {
    Write-Host ("  Stopped PIDs: {0}" -f ($killed -join ", ")) -ForegroundColor Green
    Start-Sleep -Seconds 2
  } else {
    Write-Host "  No Celery/scraper processes found (OK)." -ForegroundColor Gray
  }
} else {
  Write-Step "[3/5] Skipping process stop (-StopStack not set)."
}

Write-Step "[4/5] Preparing scraper.session..."
if ($ResetSession -or -not (Test-Path -LiteralPath $sessionFile)) {
  if (Test-Path -LiteralPath $sessionFile) {
    Remove-Item -LiteralPath $sessionFile -Force
    Write-Host "  Removed old scraper.session (-ResetSession)." -ForegroundColor Yellow
  }
  Remove-Item -LiteralPath ($sessionFile + "-journal") -Force -ErrorAction SilentlyContinue
  Write-Host "  Fresh login will create scraper.session" -ForegroundColor Gray
} else {
  Write-Host '  Existing scraper.session found - Telethon may skip phone login if already authorized.' -ForegroundColor Gray
  Write-Host "  Use -ResetSession to delete and log in again." -ForegroundColor DarkGray
}

Write-Step "[5/5] Interactive scrape (Telethon login + test run)..."
Write-Host "  When prompted:" -ForegroundColor White
Write-Host "    Phone  = international format, e.g. +15551234567 (NOT source id, NOT pool id)" -ForegroundColor White
Write-Host "    Code   = login code from Telegram app/SMS" -ForegroundColor White
Write-Host "    2FA    = Telegram password if enabled" -ForegroundColor White
Write-Host ""
Write-Host "  Do NOT press Ctrl+C while waiting for prompts." -ForegroundColor Yellow
Write-Host ""
Read-Host "Press Enter to start"

$py = Get-TbccPythonCmd
$scrapeScript = Join-Path $backendDir "scripts\run_scrape_once.py"
Push-Location -LiteralPath $backendDir
try {
  Invoke-Expression "$py `"$scrapeScript`" $SourceId"
  $exitCode = $LASTEXITCODE
} finally {
  Pop-Location
}

if ($exitCode -ne 0) {
  Write-Host ""
  Write-Host "Scrape script exited with code $exitCode." -ForegroundColor Red
  Write-Host "If login was interrupted, re-run with -ResetSession:" -ForegroundColor Yellow
  Write-Host "  .\scripts\setup-scraper-session.ps1 -SourceId $SourceId -ResetSession" -ForegroundColor Yellow
  exit $exitCode
}

Write-Host ""
Write-Host "Done. scraper.session should be authorized." -ForegroundColor Green
Write-Host "  Source $($chosen.id) delivers to pool $($chosen.pool_id)." -ForegroundColor Gray
Write-Host '  Celery Scrape now uses the same session - do not log in via the Celery tab.' -ForegroundColor Gray

if ($RestartStack) {
  Write-Host ""
  $cold = Join-Path $PSScriptRoot "tbcc-cold-start.ps1"
  if (Test-Path -LiteralPath $cold) {
    Write-Host "Starting TBCC stack (tbcc-cold-start.ps1)..." -ForegroundColor Cyan
    & $cold
  } else {
    Write-Host 'Restart manually: cd tbcc ; .\start.ps1 -Full -WtTabs' -ForegroundColor Yellow
  }
} else {
  Write-Host ""
  Write-Host "Next: start TBCC stack, then Automation -> Ingest -> Scrape now" -ForegroundColor Cyan
  Write-Host "  cd $tbccDir" -ForegroundColor DarkGray
  Write-Host '  .\start.ps1 -Full -WtTabs' -ForegroundColor DarkGray
}
