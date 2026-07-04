# Sync scraper.session from home PC to remote TBCC worker VM.
# Requires: OpenSSH client (Windows 10+), Tailscale or VPN to remote host.
#
# Usage:
#   .\scripts\remote-worker\sync-scraper-session.ps1 -RemoteHost 100.64.0.2 -RemoteUser ubuntu
#   .\scripts\remote-worker\sync-scraper-session.ps1 -RemoteHost 100.64.0.2 -RemoteUser ubuntu -IncludePoster

param(
  [Parameter(Mandatory = $true)][string]$RemoteHost,
  [Parameter(Mandatory = $true)][string]$RemoteUser,
  [string]$RemotePath = "/opt/tbcc/infra/data/sessions",
  [switch]$IncludePoster
)

$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$backend = Join-Path $tbccRoot "backend"

$files = @(
  "scraper.session",
  "scraper.session-wal",
  "scraper.session-shm"
)
if ($IncludePoster) {
  $files += @("admin_poster.session", "admin_poster.session-wal", "admin_poster.session-shm")
}

$dest = "${RemoteUser}@${RemoteHost}:${RemotePath}/"
Write-Host "Creating remote dir $RemotePath ..."
ssh "${RemoteUser}@${RemoteHost}" "mkdir -p $RemotePath"

foreach ($name in $files) {
  $local = Join-Path $backend $name
  if (-not (Test-Path -LiteralPath $local)) {
    if ($name -match '\.(wal|shm)$') { continue }
    Write-Warning "Missing $local — run setup-scraper-session.ps1 on home PC first."
    continue
  }
  Write-Host "Copying $name ..."
  scp -p $local $dest
}

Write-Host ""
Write-Host "Done. On the VM:" -ForegroundColor Green
Write-Host "  cd /opt/tbcc && bash scripts/remote-worker/install-remote-worker.sh"
