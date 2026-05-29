# Quick checks before cold start / restart. Returns exit 0 when OK, 1 when warnings.
#   . .\scripts\tbcc-stack-preflight.ps1
#   Test-TbccStackPreflight -TbccRoot $tbccDir

function Test-TbccStackPreflight {
  param([string]$TbccRoot)
  $issues = @()
  $redis = [bool](Get-NetTCPConnection -LocalPort 6379 -State Listen -ErrorAction SilentlyContinue)
  $pg = [bool](Get-NetTCPConnection -LocalPort 5432 -State Listen -ErrorAction SilentlyContinue)
  if (-not $redis) { $issues += "Redis not listening on :6379 (run: cd tbcc\infra ; docker compose -f docker-compose.infra.yml up -d redis)" }
  if (-not $pg) { $issues += "Postgres not listening on :5432 (docker compose up -d postgres)" }

  $orphans = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'multiprocessing-fork|multiprocessing\.spawn' })
  if ($orphans.Count -gt 0) {
    $cleanupScript = Join-Path $TbccRoot "scripts\tbcc-cleanup-orphans.ps1"
    if (Test-Path -LiteralPath $cleanupScript) {
      try { & powershell -NoProfile -ExecutionPolicy Bypass -File $cleanupScript 2>$null | Out-Null } catch {}
      Start-Sleep -Milliseconds 800
      $orphans = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'multiprocessing-fork|multiprocessing\.spawn' })
    }
    if ($orphans.Count -gt 0) {
      $issues += "Orphan uvicorn workers: $($orphans.Count) (auto-cleanup ran; restart stack if banner persists)"
    }
  }

  $listeners = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
  if ($listeners.Count -gt 1) {
    $issues += "Multiple listeners on :8000 ($($listeners.Count)) — API may be hung"
  }

  if ($issues.Count -eq 0) {
    return @{ ok = $true; issues = @() }
  }
  return @{ ok = $false; issues = $issues }
}

if ($MyInvocation.InvocationName -ne '.') {
  $tbccDir = Split-Path -Parent $PSScriptRoot
  $r = Test-TbccStackPreflight -TbccRoot $tbccDir
  if ($r.ok) {
    Write-Host "TBCC preflight OK" -ForegroundColor Green
    exit 0
  }
  foreach ($i in $r.issues) { Write-Host "  - $i" -ForegroundColor Yellow }
  exit 1
}
