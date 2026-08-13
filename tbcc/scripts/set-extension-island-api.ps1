# Set TBCC Importer -> island API (chrome.storage.local).
# Run after reloading the unpacked extension so Options UI is current.
#
# Usage (from tbcc/):
#   powershell -NoProfile -File .\scripts\set-extension-island-api.ps1
#   powershell -NoProfile -File .\scripts\set-extension-island-api.ps1 -ApiBase http://5.161.53.91:8000
#
# Prefers: https://api.powercore.app (island tunnel), then local tunnel, then island IP.

param(
  [string]$ApiBase = "",
  [string]$IslandPublic = "https://api.powercore.app",
  [string]$IslandIpFallback = "http://5.161.53.91:8000",
  [switch]$StartTunnel
)

$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $tbccRoot ".env"
$key = ""
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*TBCC_INTERNAL_API_KEY=(.+)$') {
      $key = $Matches[1].Trim().Trim('"').Trim("'")
    }
  }
}

function Test-Health([string]$base) {
  try {
    $r = Invoke-WebRequest -Uri ($base.TrimEnd('/') + "/health") -UseBasicParsing -TimeoutSec 5
    return $r.StatusCode -ge 200 -and $r.StatusCode -lt 300
  } catch {
    return $false
  }
}

if (-not $ApiBase) {
  if (Test-Health $IslandPublic) {
    $ApiBase = $IslandPublic.TrimEnd('/')
  } elseif (Test-Health "http://127.0.0.1:8000") {
    $ApiBase = "http://127.0.0.1:8000"
  } elseif (Test-Health $IslandIpFallback) {
    $ApiBase = $IslandIpFallback.TrimEnd('/')
  } else {
    Write-Host "No live API on $IslandPublic, 127.0.0.1:8000, or $IslandIpFallback" -ForegroundColor Red
    Write-Host "Check island: curl -fsS https://api.powercore.app/health" -ForegroundColor Yellow
    exit 1
  }
}

$ApiBase = $ApiBase.TrimEnd('/')
Write-Host "API base -> $ApiBase" -ForegroundColor Green
if ($key) { Write-Host "Internal key -> (from tbcc/.env)" -ForegroundColor Green }
else { Write-Host "Internal key -> missing in tbcc/.env (ok if REQUIRE_INTERNAL=0)" -ForegroundColor Yellow }

$outDir = Join-Path $tbccRoot ".tbcc-run"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$payload = @{
  tbccApiBase        = $ApiBase
  tbccInternalApiKey = $key
  setAt              = (Get-Date).ToString("o")
  note               = "Options -> Local stack -> Apply island seed (clipboard)"
} | ConvertTo-Json
$payloadPath = Join-Path $outDir "extension-island-api.json"
$payload | Set-Content -Path $payloadPath -Encoding utf8
Write-Host "Wrote $payloadPath" -ForegroundColor DarkGray

$seed = "TBCC_SEED|$ApiBase|$key"
try {
  Set-Clipboard -Value $seed
  Write-Host "Clipboard set to TBCC_SEED|apiBase|key (ready for Options apply)" -ForegroundColor Green
} catch {
  try {
    Set-Clipboard -Value $ApiBase
    Write-Host "API base copied to clipboard (seed copy failed)." -ForegroundColor DarkYellow
  } catch {}
}

$extPath = Join-Path $tbccRoot "extension"
$idScript = Join-Path $outDir "compute-ext-id.py"
@(
  "import hashlib",
  "p = r'''$extPath'''",
  "p = p[0].upper() + p[1:]",
  "h = hashlib.sha256(p.encode('utf-16-le')).hexdigest()",
  "print(''.join(chr(ord('a') + int(c, 16)) for c in h[:32]))"
) | Set-Content -Path $idScript -Encoding utf8

$extId = ""
try {
  $extId = (& py -3.13 $idScript | Select-Object -Last 1).ToString().Trim()
} catch {}

$optionsUrl = ""
if ($extId -match '^[a-p]{32}$') {
  $optionsUrl = "chrome-extension://$extId/model-search-options.html?apply-island-seed=1#local-stack"
  Write-Host ""
  Write-Host "Opening Brave Options to apply seed..." -ForegroundColor Cyan
  $pf86 = ${env:ProgramFiles(x86)}
  $braveCandidates = @(
    (Join-Path $env:ProgramFiles "BraveSoftware\Brave-Browser\Application\brave.exe"),
    (Join-Path $env:LOCALAPPDATA "BraveSoftware\Brave-Browser\Application\brave.exe")
  )
  if ($pf86) {
    $braveCandidates += (Join-Path $pf86 "BraveSoftware\Brave-Browser\Application\brave.exe")
  }
  $brave = $braveCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
  if ($brave) {
    Start-Process -FilePath $brave -ArgumentList @("--profile-directory=Profile 1", $optionsUrl)
  } else {
    Write-Host "Brave not found - open manually:" -ForegroundColor Yellow
    Write-Host "  $optionsUrl" -ForegroundColor DarkGray
  }
} else {
  Write-Host "Could not compute extension id - open TBCC Options -> Local stack -> Apply island seed" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "To apply in the browser (unpacked extension):" -ForegroundColor Cyan
Write-Host "  1. Reload TBCC extension (brave://extensions) so Options UI is current (1.40.32+)"
Write-Host "  2. Options -> Local stack -> Apply island seed (clipboard)  OR open:"
if ($optionsUrl) { Write-Host "     $optionsUrl" -ForegroundColor DarkGray }
Write-Host "  3. Status should say API OK @ $ApiBase (with internal key)"
Write-Host "  4. On Erome: Push to TBCC / refresh at 5000 rows"
Write-Host ""
Write-Host "Home tray Postgres error: local :5432 is down - expected on lean home." -ForegroundColor DarkYellow
Write-Host "Do NOT need local uvicorn for intel push; island API is enough." -ForegroundColor DarkYellow
Write-Host "Unblocks: intel push, promo upload, Send to TBCC, ZIP flywheel against island." -ForegroundColor Green

if ($StartTunnel) {
  Write-Host "Starting dashboard tunnel (blocking)..." -ForegroundColor Yellow
  & (Join-Path $PSScriptRoot "revenue-island\dashboard-tunnel.ps1")
}
