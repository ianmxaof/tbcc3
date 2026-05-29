# Enable loot overseer daily AOF group promo in DB + optional immediate test post.
#
#   cd tbcc
#   .\scripts\enable-loot-daily-promo.ps1
#   .\scripts\enable-loot-daily-promo.ps1 -PostNow

param(
  [switch]$PostNow
)

$ErrorActionPreference = "Stop"
$tbccDir = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $tbccDir ".env"
$backendDir = Join-Path $tbccDir "backend"
$pyScript = Join-Path $backendDir "scripts\enable_loot_daily_promo.py"

$py = "python"
try {
  & py -3.13 -c "import sys" 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) { $py = "py -3.13" }
} catch {}

if (-not (Test-Path -LiteralPath $pyScript)) {
  Write-Host "Missing $pyScript" -ForegroundColor Red
  exit 1
}

Write-Host "Enabling daily promo from tbcc\.env ..." -ForegroundColor Cyan
Push-Location $backendDir
try {
  Invoke-Expression "$py `"$pyScript`""
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
  Pop-Location
}

$hour = "18"
if (Test-Path -LiteralPath $envFile) {
  foreach ($line in Get-Content -LiteralPath $envFile) {
    if ($line -match '^TBCC_LOOT_DAILY_PROMO_HOUR_UTC=(\d+)') {
      $hour = $Matches[1]
      break
    }
  }
}

Write-Host ""
Write-Host "Celery Beat task loot-daily-promo fires every hour at :00 UTC." -ForegroundColor Green
Write-Host "Automatic post when UTC hour is $hour (needs TBCC-Beat + TBCC-Celery running)." -ForegroundColor Gray
Write-Host "Restart TBCC-Beat after pulling code so loot_promo_worker is registered." -ForegroundColor Yellow

if ($PostNow) {
  $apiKey = $null
  if (Test-Path -LiteralPath $envFile) {
    foreach ($line in Get-Content -LiteralPath $envFile) {
      if ($line -match '^TBCC_INTERNAL_API_KEY=(.+)$') {
        $apiKey = $Matches[1].Trim().Trim('"')
        break
      }
    }
  }
  if (-not $apiKey) {
    Write-Host "TBCC_INTERNAL_API_KEY missing in .env" -ForegroundColor Red
    exit 1
  }
  $uri = "http://127.0.0.1:8000/loot-bot-settings/trigger-daily-promo"
  Write-Host "POST $uri ..." -ForegroundColor Cyan
  try {
    $r = Invoke-RestMethod -Uri $uri -Method Post -Headers @{ "X-TBCC-Internal-Key" = $apiKey } -TimeoutSec 30
    Write-Host ("Queued: " + ($r | ConvertTo-Json -Compress)) -ForegroundColor Green
    Write-Host "Check TBCC-Celery tab; message should appear in the AOF group shortly." -ForegroundColor Gray
  } catch {
    Write-Host ("API failed: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host "Start TBCC-Backend and TBCC-Celery, then re-run with -PostNow." -ForegroundColor Yellow
    exit 1
  }
} else {
  Write-Host ""
  Write-Host "Test: .\scripts\enable-loot-daily-promo.ps1 -PostNow" -ForegroundColor Gray
}
