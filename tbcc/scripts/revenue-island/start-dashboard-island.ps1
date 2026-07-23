# Start TBCC dashboard pointed at production island by default.
# Requires TBCC_INTERNAL_API_KEY in tbcc/.env (same key as island API).
#
#   .\scripts\revenue-island\start-dashboard-island.ps1
#
# Then open http://127.0.0.1:5173 — use header Island | Local to switch targets.

$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$dash = Join-Path $tbccRoot "dashboard"

if (-not (Test-Path (Join-Path $tbccRoot ".env"))) {
  Write-Host "Missing tbcc/.env — copy from .env.example and set TBCC_INTERNAL_API_KEY." -ForegroundColor Red
  exit 1
}

$keyLine = Select-String -Path (Join-Path $tbccRoot ".env") -Pattern '^\s*TBCC_INTERNAL_API_KEY=' -ErrorAction SilentlyContinue
if (-not $keyLine) {
  Write-Host "TBCC_INTERNAL_API_KEY not set in tbcc/.env — island proxy will 403." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "TBCC dashboard → production island (api.powercore.app)" -ForegroundColor Cyan
Write-Host "  http://127.0.0.1:5173" -ForegroundColor Green
Write-Host "  Switch Local | Island in the dashboard header anytime." -ForegroundColor DarkGray
Write-Host ""

Push-Location $dash
try {
  npm run dev:island
} finally {
  Pop-Location
}
