# One-shot: lean home PC + island API (no local backend required).
#
# Usage (from tbcc/):
#   powershell -NoProfile -File .\scripts\island-home-workstation.ps1
#
# What it does:
#   1. Seeds extension clipboard (https://api.powercore.app + internal key from tbcc/.env)
#   2. Opens Brave TBCC Options to apply seed
#   3. Prints dashboard island-mode command (npm run dev:island)
#
# Home tray backend / Postgres stay OFF - extension + dashboard talk to revenue island.

param(
  [string]$ApiBase = "https://api.powercore.app",
  [switch]$SkipBraveOpen
)

$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path $PSScriptRoot -Parent

Write-Host "=== TBCC island home workstation ===" -ForegroundColor Cyan
Write-Host "API: $ApiBase (revenue island; home backend not required)" -ForegroundColor Green

& (Join-Path $PSScriptRoot "set-extension-island-api.ps1") -ApiBase $ApiBase

Write-Host ""
Write-Host "Dashboard (island DB truth):" -ForegroundColor Cyan
Write-Host "  cd $tbccRoot\dashboard" -ForegroundColor DarkGray
Write-Host "  npm run dev:island" -ForegroundColor DarkGray
Write-Host "  open http://localhost:5173 with header target Island" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Extension checklist:" -ForegroundColor Cyan
Write-Host "  1. brave://extensions -> Reload TBCC" -ForegroundColor DarkGray
Write-Host "  2. Options -> Local stack -> Apply island seed (clipboard)" -ForegroundColor DarkGray
Write-Host "  3. Context menu / gallery / Save AOF use island API" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Telethon scrape routes still need local admin.session." -ForegroundColor DarkYellow
Write-Host "Beacon paste table: docs/WK31_BEACON_PASTE.md" -ForegroundColor DarkGray

if ($SkipBraveOpen) {
  Write-Host "Skipped Brave open (-SkipBraveOpen)" -ForegroundColor DarkGray
}
