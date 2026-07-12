# One-time bootstrap: GCP VM + Tailscale mesh + home offload + session + GHCR worker.
#
# Run once when standing up remote scrape offload. Daily launches use launch-remote-worker.ps1
# (called automatically from start.ps1 when TBCC_REMOTE_STACK_HOST is set).
#
# Usage:
#   cd tbcc
#   .\scripts\remote-worker\setup-remote-worker.ps1 -ProjectId tbcc-cloud-instance -RemoteHost 100.x.y.z
#   .\scripts\remote-worker\setup-remote-worker.ps1 -SkipCreateVm   # VM already exists
#
param(
  [string]$ProjectId = "tbcc-cloud-instance",
  [string]$Zone = "us-west1-a",
  [string]$InstanceName = "tbcc-remote-worker",
  [Parameter(Mandatory = $true)][string]$RemoteHost,
  [string]$RemoteUser = "ianm_powercore_gmail_com",
  [switch]$SkipCreateVm,
  [switch]$SkipSessionSync,
  [switch]$SkipGhcrPush,
  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$here = $PSScriptRoot

Write-Host "TBCC remote worker — ONE-TIME SETUP" -ForegroundColor Cyan
Write-Host "  VM Tailscale IP: $RemoteHost"
Write-Host ""

if (-not $SkipCreateVm) {
  & (Join-Path $here "create-gcp-vm.ps1") -ProjectId $ProjectId -Zone $Zone -InstanceName $InstanceName -UseGhcr -WhatIf:$WhatIf
  if ($WhatIf) { exit 0 }
  Write-Host "Waiting 90s for startup-script (Tailscale + Docker + clone)..." -ForegroundColor Yellow
  Start-Sleep -Seconds 90
}

& (Join-Path $here "install-tailscale-home.ps1") -BindInfraPorts
& (Join-Path $here "enable-home-offload.ps1") -RemoteHost $RemoteHost -RemoteUser $RemoteUser

if (-not $SkipSessionSync) {
  & (Join-Path $here "sync-scraper-session.ps1") -RemoteHost $RemoteHost -RemoteUser $RemoteUser -ViaGcloud -ProjectId $ProjectId -Zone $Zone -InstanceName $InstanceName
}

& (Join-Path $here "sync-remote-worker-scripts.ps1") -ViaGcloud -ProjectId $ProjectId -Zone $Zone -InstanceName $InstanceName

if (-not $SkipGhcrPush) {
  & (Join-Path $here "push-ghcr-worker.ps1")
}
& (Join-Path $here "update-remote-worker.ps1") -ViaGcloud -ProjectId $ProjectId -Zone $Zone -InstanceName $InstanceName

Write-Host ""
Write-Host "Setup complete. Routine launches: .\start.ps1 -Full -WtTabs (includes remote worker tab + ensure step)." -ForegroundColor Green
Write-Host "Status: .\scripts\remote-worker\status-remote-worker.ps1" -ForegroundColor Gray
