# Install Tailscale on home Windows PC for TBCC remote scrape worker mesh.
# Same tailnet as the GCP VM (log in with the same Google account on both).
#
# Usage:
#   cd tbcc
#   .\scripts\remote-worker\install-tailscale-home.ps1
#   .\scripts\remote-worker\install-tailscale-home.ps1 -BindInfraPorts   # patch tailscale-bind + firewall
#
param(
  # Open browser login after install (required once per machine)
  [switch]$Login = $true,

  # Patch infra/docker-compose.tailscale-bind.yml with this PC's Tailscale IP
  # and add Windows Firewall rules for Postgres/Redis on the Tailscale adapter
  [switch]$BindInfraPorts
)

$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$infra = Join-Path $tbccRoot "infra"
$bindFile = Join-Path $infra "docker-compose.tailscale-bind.yml"

Write-Host "TBCC home Tailscale setup" -ForegroundColor Cyan
Write-Host ""

# --- Install ---
$ts = Get-Command tailscale -ErrorAction SilentlyContinue
if (-not $ts) {
  Write-Host "Installing Tailscale via winget..." -ForegroundColor Yellow
  winget install --id Tailscale.Tailscale -e --accept-package-agreements --accept-source-agreements
  $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
    [System.Environment]::GetEnvironmentVariable("Path", "User")
  $ts = Get-Command tailscale -ErrorAction SilentlyContinue
  if (-not $ts) {
    throw "tailscale not on PATH after install. Open a new PowerShell window and re-run."
  }
} else {
  Write-Host "Tailscale already installed: $($ts.Source)" -ForegroundColor DarkGray
}

# --- Service ---
$svc = Get-Service -Name Tailscale -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -ne "Running") {
  Write-Host "Starting Tailscale service..." -ForegroundColor Yellow
  Start-Service Tailscale
}

# --- Login (interactive - browser) ---
if ($Login) {
  Write-Host ""
  Write-Host "Opening Tailscale login - use the SAME account you will use on the GCP VM." -ForegroundColor Yellow
  Write-Host "Recommended account: ianm.powercore@gmail.com" -ForegroundColor DarkGray
  & tailscale up
  if ($LASTEXITCODE -ne 0) {
    throw "tailscale up failed (exit $LASTEXITCODE)"
  }
}

# --- Status ---
Write-Host ""
& tailscale status
$homeIp = (& tailscale ip -4 2>$null | Select-Object -First 1).Trim()
if (-not $homeIp) {
  Write-Host ""
  Write-Host "Not connected yet. Run: tailscale up" -ForegroundColor Yellow
  exit 1
}

Write-Host ""
Write-Host "Home Tailscale IPv4: $homeIp" -ForegroundColor Green

if ($BindInfraPorts) {
  if (-not (Test-Path -LiteralPath $bindFile)) {
    throw "Missing $bindFile"
  }
  $content = Get-Content -LiteralPath $bindFile -Raw
  $updated = $content -replace '100\.64\.0\.1', $homeIp
  if ($updated -eq $content) {
    Write-Host "docker-compose.tailscale-bind.yml already uses $homeIp (or no placeholder found)." -ForegroundColor DarkGray
  } else {
    Set-Content -LiteralPath $bindFile -Value $updated -NoNewline
    Write-Host "Patched $bindFile -> $homeIp" -ForegroundColor Green
  }

  Write-Host "Adding Windows Firewall rules (Tailscale adapter, Postgres + Redis)..." -ForegroundColor Yellow
  $rules = @(
    @{ Name = "TBCC Postgres (Tailscale)"; Port = 5432 },
    @{ Name = "TBCC Redis (Tailscale)"; Port = 6379 }
  )
  foreach ($r in $rules) {
    $existing = Get-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue
    if ($existing) {
      Write-Host "  $($r.Name) — already exists" -ForegroundColor DarkGray
      continue
    }
    New-NetFirewallRule -DisplayName $r.Name -Direction Inbound -Action Allow `
      -Protocol TCP -LocalPort $r.Port -InterfaceAlias "Tailscale*" -Profile Private | Out-Null
    Write-Host "  $($r.Name) — created" -ForegroundColor Green
  }

  Write-Host ""
  Write-Host "Restart infra with Tailscale bind:" -ForegroundColor Cyan
  Write-Host "  cd $infra"
  Write-Host "  docker compose -f docker-compose.infra.yml -f docker-compose.tailscale-bind.yml up -d"
}

Write-Host ""
Write-Host "Next — on GCP VM (after: sudo apt-get install -y curl):" -ForegroundColor Cyan
Write-Host "  curl -fsSL https://tailscale.com/install.sh | sh"
Write-Host "  sudo tailscale up    # same Google account"
Write-Host "  tailscale ip -4      # note VM IP for .env.remote-worker"
Write-Host ""
Write-Host "Then sync scraper.session (use your VM OS Login user, not ubuntu):" -ForegroundColor Cyan
Write-Host "  .\scripts\remote-worker\sync-scraper-session.ps1 -RemoteHost <vm-tailscale-ip> -RemoteUser ianm_powercore_gmail_com"
