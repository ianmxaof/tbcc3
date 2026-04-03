# One-shot: ngrok tunnel -> set TBCC_PROMO_PUBLIC_BASE_URL in tbcc/.env -> restart API (+ payment bot).
#
# Prerequisites: ngrok installed + `ngrok config add-authtoken ...` done once.
#
# Usage (from tbcc folder):
#   .\setup-promo-tunnel.ps1
#   .\setup-promo-tunnel.ps1 -SkipDocker          # skip postgres/redis compose
#   .\setup-promo-tunnel.ps1 -ApiOnly              # after .env update, only restart API (not payment bot)
#
# What it does:
#   1) Optional: docker compose up postgres + redis (same infra file as start.ps1)
#   2) Start ngrok http 8000 in a new window if the ngrok web UI (:4040) is not up
#   3) Read https public URL from http://127.0.0.1:4040/api/tunnels
#   4) Write TBCC_PROMO_PUBLIC_BASE_URL=... to tbcc/.env (no trailing slash)
#   5) Run .\restart-api-payment.ps1 (or -ApiOnly)

$ErrorActionPreference = "Continue"
$tbccDir = $PSScriptRoot
$backendDir = Join-Path $tbccDir "backend"
$envFile = Join-Path $tbccDir ".env"

$skipDocker = $args -contains "-SkipDocker"
$apiOnlyRestart = ($args -contains "-ApiOnly") -or ($args -contains "-NoPaymentBot")

function Start-TbccCmdWindow {
  param([string]$Title, [string]$Command)
  $run = 'title "' + $Title + '" && ' + $Command
  Start-Process -FilePath $env:ComSpec -ArgumentList @("/k", $run) -WindowStyle Normal
}

function Get-NgrokHttpsUrl {
  param([int]$MaxWaitSec = 90)
  $deadline = (Get-Date).AddSeconds($MaxWaitSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $resp = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 3 -ErrorAction Stop
      foreach ($t in $resp.tunnels) {
        if ($t.public_url -and $t.public_url -like "https://*") {
          $u = $t.public_url.TrimEnd('/')
          return $u
        }
      }
    } catch {}
    Start-Sleep -Seconds 1
  }
  return $null
}

function Set-DotEnvKey {
  param([string]$Path, [string]$Key, [string]$Value)
  if (-not (Test-Path $Path)) {
    throw "Missing file: $Path"
  }
  $raw = [System.IO.File]::ReadAllText($Path)
  $pattern = "(?m)^\s*#?\s*" + [regex]::Escape($Key) + "=.*$"
  if ($raw -match $pattern) {
    $raw = $raw -replace $pattern, ($Key + "=" + $Value)
  } else {
    $nl = "`r`n"
    if (-not $raw.EndsWith("`n")) { $raw += $nl }
    $raw += $Key + "=" + $Value + $nl
  }
  [System.IO.File]::WriteAllText($Path, $raw)
}

Write-Host ""
Write-Host 'TBCC setup-promo-tunnel (ngrok, TBCC_PROMO_PUBLIC_BASE_URL, restart)' -ForegroundColor Cyan
Write-Host ""

if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
  Write-Host 'ngrok not found in PATH. Install from https://ngrok.com/download and run:' -ForegroundColor Red
  Write-Host '  ngrok config add-authtoken YOUR_TOKEN' -ForegroundColor Yellow
  exit 1
}

# 0. Docker (optional)
if (-not $skipDocker) {
  $infraCompose = Join-Path $tbccDir "infra\docker-compose.infra.yml"
  $legacyCompose = Join-Path $tbccDir "infra\docker-compose.yml"
  $composeFile = if (Test-Path $infraCompose) { $infraCompose } elseif (Test-Path $legacyCompose) { $legacyCompose } else { $null }
  if ($composeFile) {
    Write-Host ('[0] Docker: postgres + redis ' + [IO.Path]::GetFileName($composeFile) + ' ...') -ForegroundColor Yellow
    Push-Location (Join-Path $tbccDir "infra")
    try {
      $composeName = [IO.Path]::GetFileName($composeFile)
      if ($composeName -eq 'docker-compose.infra.yml') {
        cmd /c 'docker compose -f docker-compose.infra.yml up -d postgres redis' 2>$null
      } elseif (Test-Path $envFile) {
        $ef = (Resolve-Path $envFile).Path
        cmd /c ('docker compose --env-file "' + $ef + '" -f "' + $composeName + '" up -d postgres redis') 2>$null
      } else {
        cmd /c ('docker compose -f "' + $composeName + '" up -d postgres redis') 2>$null
      }
    } finally {
      Pop-Location
    }
    Start-Sleep -Seconds 2
  } else {
    Write-Host '[0] No infra compose file — skip Docker.' -ForegroundColor DarkYellow
  }
} else {
  Write-Host '[0] Skipping Docker (-SkipDocker).' -ForegroundColor DarkYellow
}

# 1. ngrok local API (4040) — start tunnel if needed
$needNgrok = $true
try {
  $null = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2 -ErrorAction Stop
  $needNgrok = $false
} catch {
  $needNgrok = $true
}

if ($needNgrok) {
  Write-Host '[1] Starting ngrok (new window) to http 8000 ...' -ForegroundColor Yellow
  Start-TbccCmdWindow -Title "TBCC-ngrok" -Command "ngrok http 8000"
  Start-Sleep -Seconds 2
} else {
  Write-Host '[1] ngrok web UI already on :4040 (reusing).' -ForegroundColor Green
}

$publicUrl = Get-NgrokHttpsUrl -MaxWaitSec 90
if (-not $publicUrl) {
  Write-Host 'Could not read https URL from ngrok http://127.0.0.1:4040/api/tunnels .' -ForegroundColor Red
  Write-Host 'Check the TBCC-ngrok window: authtoken, firewall, or port conflict.' -ForegroundColor Yellow
  exit 1
}

Write-Host ('  Public HTTPS URL: ' + $publicUrl) -ForegroundColor Green

# 2. .env
Write-Host '[2] Writing TBCC_PROMO_PUBLIC_BASE_URL to tbcc .env file ...' -ForegroundColor Yellow
Set-DotEnvKey -Path $envFile -Key 'TBCC_PROMO_PUBLIC_BASE_URL' -Value $publicUrl
Write-Host ('  OK: TBCC_PROMO_PUBLIC_BASE_URL=' + $publicUrl) -ForegroundColor Green

# 3. Restart API (+ optional payment bot) so process reloads env
Write-Host '[3] Restarting API (loads new env) ...' -ForegroundColor Yellow
$restartArgs = @()
if ($apiOnlyRestart) { $restartArgs += '-ApiOnly' }
$restartScript = Join-Path $tbccDir 'restart-api-payment.ps1'
& $restartScript @restartArgs
if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
  Write-Host ('restart-api-payment.ps1 exited with code ' + $LASTEXITCODE) -ForegroundColor Yellow
}

Write-Host ""
Write-Host 'Next steps (manual):' -ForegroundColor Cyan
Write-Host '  - Dashboard, Bots, Shop: use Upload again on promo images (old localhost URLs stay wrong until re-upload).' -ForegroundColor Gray
Write-Host ('  - Test in browser: ' + $publicUrl + '/static/promo/sample.jpg') -ForegroundColor Gray
Write-Host ""
