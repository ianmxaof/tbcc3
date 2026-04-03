# Quick TBCC backend / DB check (PowerShell)
# Usage: .\check-backend.ps1   from tbcc folder

$ErrorActionPreference = "SilentlyContinue"
Write-Host "TBCC connectivity check" -ForegroundColor Cyan
Write-Host ""

# Postgres (from .env default)
$pg = Test-NetConnection -ComputerName 127.0.0.1 -Port 5432 -WarningAction SilentlyContinue
if ($pg.TcpTestSucceeded) {
  Write-Host "  [OK] Postgres reachable on :5432" -ForegroundColor Green
} else {
  Write-Host "  [FAIL] Postgres not reachable on :5432 — start: cd infra ; docker compose -f docker-compose.infra.yml up -d postgres" -ForegroundColor Red
}

# API
$apiOk = $false
try {
  $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
  if ($r.StatusCode -eq 200) { $apiOk = $true }
} catch {
  $apiOk = $false
}
if ($apiOk) {
  Write-Host "  [OK] API http://127.0.0.1:8000/health" -ForegroundColor Green
} else {
  Write-Host "  [FAIL] Nothing on port 8000 — backend not running." -ForegroundColor Red
  Write-Host "         Start: cd backend ; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-exclude scripts --reload-delay 1" -ForegroundColor Yellow
  Write-Host "         Or:    .\start.ps1   (opens TBCC-Backend window)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Dashboard expects the Vite proxy to reach this API (see dashboard vite.config)." -ForegroundColor Gray
