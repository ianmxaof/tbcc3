# Start Cloudflare named-tunnel setup on the revenue island.
# Step 1 prints a login URL (open in browser, pick powercore.app zone).
# Step 2 installs api.powercore.app -> localhost:8000 and patches island env.
#
#   .\scripts\revenue-island\setup-island-named-tunnel.ps1
#   .\scripts\revenue-island\setup-island-named-tunnel.ps1 -HostName root@5.161.53.91 -Hostname api.powercore.app

param(
  [string]$HostName = "root@5.161.53.91",
  [string]$RemoteDir = "/opt/tbcc",
  [string]$Hostname = "api.powercore.app",
  [switch]$SkipLogin
)

$ErrorActionPreference = "Stop"
$tbccRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$scriptLocal = Join-Path $PSScriptRoot "install-island-named-tunnel.sh"

Write-Host "=== Named Cloudflare tunnel -> $Hostname ===" -ForegroundColor Cyan

& (Join-Path $PSScriptRoot "sync-island-files.ps1") -HostName $HostName
& scp $scriptLocal "${HostName}:$RemoteDir/scripts/revenue-island/"
& ssh $HostName "sed -i 's/\r$//' $RemoteDir/scripts/revenue-island/install-island-named-tunnel.sh && chmod +x $RemoteDir/scripts/revenue-island/install-island-named-tunnel.sh"

if (-not $SkipLogin) {
  Write-Host ""
  Write-Host "[1/2] Cloudflare login (one-time) — open the URL below in your browser:" -ForegroundColor Yellow
  Write-Host "      Pick zone: powercore.app (or the zone that owns $Hostname)" -ForegroundColor DarkGray
  Write-Host ""
  & ssh -t $HostName "cloudflared tunnel login"
  Write-Host ""
}

Write-Host "[2/2] Create tunnel + route DNS + patch island env..." -ForegroundColor Yellow
& ssh $HostName "CF_HOSTNAME=$Hostname bash $RemoteDir/scripts/revenue-island/install-island-named-tunnel.sh"

Write-Host ""
Write-Host "Recreating api + payment_bot with new public URL..." -ForegroundColor Yellow
& ssh $HostName "cd $RemoteDir/infra && docker compose -f docker-compose.revenue-island.yml --env-file .env.revenue-island up -d --pull never --force-recreate api payment_bot worker worker_telegram worker_post beat"

Write-Host ""
& (Join-Path $PSScriptRoot "wire-island-webhooks.ps1") -HostName $HostName
Write-Host ""
Write-Host "Gumroad Ping URL should now be: https://${Hostname}/webhooks/gumroad" -ForegroundColor Green
Write-Host "Remove old Vercel DNS for $Hostname in Cloudflare if the tunnel route did not replace it." -ForegroundColor Yellow
