# Status check for remote scrape offload (home + optional Tailscale ping).
#
# Usage:
#   .\scripts\remote-worker\status-remote-worker.ps1
#
param(
  [string]$RemoteHost = "",
  [string]$RemoteUser = "ubuntu"
)

$ErrorActionPreference = "Continue"
$tbccRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$envFile = Join-Path $tbccRoot ".env"

function Get-EnvVal([string]$Name) {
  if (-not (Test-Path -LiteralPath $envFile)) { return "" }
  foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
    if ($line -match "^\s*$([regex]::Escape($Name))\s*=\s*(.*)$") {
      return $Matches[1].Trim().Trim('"').Trim("'")
    }
  }
  return ""
}

if (-not $RemoteHost) { $RemoteHost = Get-EnvVal "TBCC_REMOTE_STACK_HOST" }
$userEnv = Get-EnvVal "TBCC_REMOTE_STACK_USER"
if ($userEnv) { $RemoteUser = $userEnv }
$homeQueues = Get-EnvVal "TBCC_CELERY_HOME_QUEUES"
$homeTs = Get-EnvVal "TBCC_HOME_TAILSCALE_IP"
if (-not $homeTs) {
  try { $homeTs = (& tailscale ip -4 2>$null | Select-Object -First 1).Trim() } catch { }
}

Write-Host "TBCC remote worker status" -ForegroundColor Cyan
Write-Host "  TBCC_REMOTE_STACK_HOST = $(if ($RemoteHost) { $RemoteHost } else { '(unset)' })"
Write-Host "  TBCC_CELERY_HOME_QUEUES = $(if ($homeQueues) { $homeQueues } else { '(unset - home may still consume scrape)' })"
Write-Host "  Home Tailscale IP      = $(if ($homeTs) { $homeTs } else { '(unknown)' })"

if ($homeQueues -and $homeQueues -match "scrape") {
  Write-Host "  WARN: home queues still include scrape - dual consumers risk session lock." -ForegroundColor Yellow
} elseif ($homeQueues) {
  Write-Host "  Home Celery excludes scrape - good." -ForegroundColor Green
}

if ($RemoteHost) {
  Write-Host "  Tailscale ping $RemoteHost ..." -ForegroundColor Gray
  & tailscale ping -c 1 --timeout 5s $RemoteHost 2>&1 | Out-Null
  if ($LASTEXITCODE -eq 0) {
    Write-Host "  Remote reachable on tailnet." -ForegroundColor Green
    Write-Host "  Checking docker worker via SSH..." -ForegroundColor Gray
    $cmd = "docker compose -f /opt/tbcc/infra/docker-compose.remote-worker.ghcr.yml ps 2>/dev/null || docker compose -f /opt/tbcc/infra/docker-compose.remote-worker.yml ps 2>/dev/null"
    ssh -o ConnectTimeout=8 "${RemoteUser}@${RemoteHost}" $cmd 2>&1 | ForEach-Object { Write-Host "    $_" }
  } else {
    Write-Host "  Remote NOT reachable (VM off / Tailscale down / wrong IP)." -ForegroundColor Yellow
    Write-Host "  Try: .\scripts\remote-worker\connect-gcp-vm.ps1 -Logs" -ForegroundColor DarkYellow
  }
} else {
  Write-Host "  Set TBCC_REMOTE_STACK_HOST or pass -RemoteHost." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Local Docker (home) - keep lean when offloading:" -ForegroundColor Cyan
try {
  docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>$null
} catch {
  Write-Host "  docker stats unavailable" -ForegroundColor DarkGray
}
