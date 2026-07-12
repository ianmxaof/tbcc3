# Enable home-side offload: exclude scrape from local Celery + set remote host.
#
# Usage:
#   cd tbcc
#   .\scripts\remote-worker\enable-home-offload.ps1 -RemoteHost 100.x.y.z
#   .\scripts\remote-worker\enable-home-offload.ps1 -RemoteHost 100.x.y.z -RemoteUser ubuntu -Disable
#
param(
  [Parameter(Mandatory = $true)][string]$RemoteHost,
  [string]$RemoteUser = "ubuntu",
  [string]$RemotePath = "/opt/tbcc",
  [switch]$Disable,
  [switch]$SkipTailscaleBind
)

$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$envPath = Join-Path $tbccRoot ".env"
if (-not (Test-Path -LiteralPath $envPath)) {
  throw ".env not found at $envPath"
}

function Set-EnvKey([string]$Key, [string]$Value) {
  $lines = Get-Content -LiteralPath $envPath -Encoding UTF8
  $found = $false
  $out = foreach ($line in $lines) {
    if ($line -match "^\s*$([regex]::Escape($Key))\s*=") {
      $found = $true
      "$Key=$Value"
    } else {
      $line
    }
  }
  if (-not $found) { $out += "$Key=$Value" }
  Set-Content -LiteralPath $envPath -Value $out -Encoding UTF8
}

function Remove-EnvKeyCommentOnly([string]$Key) {
  # Soft-disable: comment active assignment
  $lines = Get-Content -LiteralPath $envPath -Encoding UTF8
  $out = foreach ($line in $lines) {
    if ($line -match "^\s*$([regex]::Escape($Key))\s*=") {
      "# $line"
    } else {
      $line
    }
  }
  Set-Content -LiteralPath $envPath -Value $out -Encoding UTF8
}

# Detect home Tailscale IP for docker bind docs
$homeTs = ""
try {
  $homeTs = (& tailscale ip -4 2>$null | Select-Object -First 1)
  if ($homeTs) { $homeTs = $homeTs.Trim() }
} catch { }

if ($Disable) {
  Write-Host "Disabling remote offload - restoring scrape on home Celery..." -ForegroundColor Yellow
  Remove-EnvKeyCommentOnly "TBCC_REMOTE_STACK_HOST"
  Remove-EnvKeyCommentOnly "TBCC_CELERY_HOME_QUEUES"
  Write-Host "Commented TBCC_REMOTE_STACK_HOST / TBCC_CELERY_HOME_QUEUES." -ForegroundColor Green
  Write-Host "Restart TBCC-Celery from tray so it consumes scrape again." -ForegroundColor Cyan
  exit 0
}

Write-Host "Enabling remote scrape offload..." -ForegroundColor Cyan
Set-EnvKey "TBCC_REMOTE_STACK_HOST" $RemoteHost
Set-EnvKey "TBCC_REMOTE_STACK_USER" $RemoteUser
Set-EnvKey "TBCC_REMOTE_STACK_PATH" $RemotePath
# Keep ops queues on home if ops worker exists; scrape leaves home.
Set-EnvKey "TBCC_CELERY_HOME_QUEUES" "celery,subscription,telegram"
if ($homeTs) {
  Set-EnvKey "TBCC_HOME_TAILSCALE_IP" $homeTs
}

Write-Host "  TBCC_REMOTE_STACK_HOST=$RemoteHost" -ForegroundColor Green
Write-Host "  TBCC_CELERY_HOME_QUEUES=celery,subscription,telegram" -ForegroundColor Green
if ($homeTs) {
  Write-Host "  TBCC_HOME_TAILSCALE_IP=$homeTs" -ForegroundColor Green
}

if (-not $SkipTailscaleBind) {
  $infra = Join-Path $tbccRoot "infra"
  $bindYml = Join-Path $infra "docker-compose.tailscale-bind.yml"
  if ((Test-Path -LiteralPath $bindYml) -and $homeTs) {
    Write-Host "Applying Tailscale bind for Postgres/Redis ($homeTs)..." -ForegroundColor Yellow
    # Patch placeholder IPs in bind file if still default
    $bindText = Get-Content -LiteralPath $bindYml -Raw -Encoding UTF8
    if ($bindText -match "100\.64\.0\.1" -and $homeTs -ne "100.64.0.1") {
      Write-Host "  Update docker-compose.tailscale-bind.yml ports to $homeTs if needed." -ForegroundColor DarkYellow
    }
    Push-Location $infra
    try {
      docker compose -f docker-compose.infra.yml -f docker-compose.tailscale-bind.yml up -d
    } catch {
      Write-Host "  docker compose bind skipped: $_" -ForegroundColor Yellow
    } finally {
      Pop-Location
    }
  }
}

Write-Host ""
Write-Host "Next:" -ForegroundColor Cyan
Write-Host "  1. Restart TBCC-Celery (tray) so scrape is no longer consumed locally."
Write-Host "  2. .\scripts\remote-worker\sync-scraper-session.ps1 -RemoteHost $RemoteHost -RemoteUser $RemoteUser"
Write-Host "  3. On VM: TBCC_USE_GHCR=1 bash /opt/tbcc/scripts/remote-worker/install-remote-worker.sh"
Write-Host "  4. .\scripts\remote-worker\status-remote-worker.ps1"
Write-Host ""
Write-Host "CPU win: heavy Telethon scrapes leave this PC. Keep Docker Desktop lean (infra only)." -ForegroundColor DarkYellow
