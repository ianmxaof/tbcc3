# Prints values to paste into TBCC Options -> Local stack (does not print secrets).
# Island has no Tailscale yet -- use public API host until MagicDNS exists.
#
#   cd tbcc
#   .\tools\set-ext-api-base-hint.ps1

$ErrorActionPreference = "Stop"
$tbccRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envFile = Join-Path $tbccRoot ".env"

Write-Host "Extension Options -> Local stack" -ForegroundColor Cyan
Write-Host "  Prefer Tailscale MagicDNS when island is online:" -ForegroundColor Green
Write-Host "    http://tbcc-revenue-island:8000" -ForegroundColor Green
Write-Host "  Fallback (public, until firewall closes :8000):" -ForegroundColor DarkYellow
Write-Host "    http://5.161.53.91:8000" -ForegroundColor DarkYellow
Write-Host "  Do not use tbcc-remote-worker (that is GCP scrape only)." -ForegroundColor DarkYellow
Write-Host ""
Write-Host "  TBCC internal key: paste TBCC_INTERNAL_API_KEY from tbcc\.env" -ForegroundColor Green
Write-Host "  (same value the island uses; Options field is password-masked)" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Then reload the TBCC extension (chrome://extensions -> Reload)." -ForegroundColor Cyan
Write-Host "Island has TBCC_API_REQUIRE_INTERNAL=1 -- key is required for imports/zip." -ForegroundColor DarkYellow

if (Test-Path -LiteralPath $envFile) {
  $has = $false
  foreach ($line in Get-Content -LiteralPath $envFile) {
    if ($line -match "^\s*TBCC_INTERNAL_API_KEY\s*=\s*\S") { $has = $true; break }
  }
  if ($has) {
    Write-Host "Home .env has TBCC_INTERNAL_API_KEY (ready to paste)." -ForegroundColor DarkGreen
  } else {
    Write-Host "WARNING: TBCC_INTERNAL_API_KEY missing from home .env" -ForegroundColor Red
  }
}
