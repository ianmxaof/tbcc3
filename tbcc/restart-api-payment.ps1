# Restart TBCC FastAPI (port 8000) and optionally the payment bot — picks up tbcc/.env changes.
#
# Usage (from tbcc folder):
#   .\restart-api-payment.ps1                 — kill :8000 + payment_bot, restart both
#   .\restart-api-payment.ps1 -ApiOnly        — only restart the API
#   .\restart-api-payment.ps1 -NoPaymentBot   — restart API only (same as -ApiOnly)
#
# Close is graceful for the API (taskkill on the listener PID). If nothing is listening, it just starts fresh windows.

$ErrorActionPreference = "Continue"
$tbccDir = $PSScriptRoot
$backendDir = Join-Path $tbccDir "backend"

$apiOnly = ($args -contains "-ApiOnly") -or ($args -contains "-NoPaymentBot")

function Stop-ListenersOnPort {
  param([int]$Port)
  $killed = @()
  if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
    $pids = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($p in $pids) {
      if ($p -and $p -gt 4) {
        try {
          Stop-Process -Id $p -Force -ErrorAction Stop
          $killed += $p
        } catch {}
      }
    }
  }
  if ($killed.Count -eq 0) {
    # Fallback: parse netstat (Windows)
    $raw = netstat -ano 2>$null | Select-String ":$Port\s"
    foreach ($line in $raw) {
      if ($line -match '\s+(\d+)\s*$') {
        $pid = [int]$Matches[1]
        if ($pid -gt 4) {
          try {
            Stop-Process -Id $pid -Force -ErrorAction Stop
            $killed += $pid
          } catch {}
        }
      }
    }
  }
  return $killed
}

function Stop-PaymentBotProcesses {
  $killed = @()
  try {
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object {
        $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -match 'bots\.payment_bot'
      }
    foreach ($pr in $procs) {
      try {
        Stop-Process -Id $pr.ProcessId -Force -ErrorAction Stop
        $killed += $pr.ProcessId
      } catch {}
    }
  } catch {}
  return $killed
}

function Start-TbccCmdWindow {
  param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$Command
  )
  $run = 'title "' + $Title + '" && ' + $Command
  Start-Process -FilePath $env:ComSpec -ArgumentList @("/k", $run) -WindowStyle Normal
}

Write-Host "TBCC restart (API + payment bot)" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1] Stopping listener(s) on port 8000..." -ForegroundColor Yellow
$p8000 = Stop-ListenersOnPort -Port 8000
if ($p8000.Count -gt 0) {
  Write-Host "  Stopped PID(s): $($p8000 -join ', ')" -ForegroundColor Green
} else {
  Write-Host "  No process was listening on :8000 (starting fresh)." -ForegroundColor Gray
}

if (-not $apiOnly) {
  Write-Host "[2] Stopping payment bot (python ... bots.payment_bot)..." -ForegroundColor Yellow
  $pp = Stop-PaymentBotProcesses
  if ($pp.Count -gt 0) {
    Write-Host "  Stopped PID(s): $($pp -join ', ')" -ForegroundColor Green
  } else {
    Write-Host "  No matching payment bot process (or not started from this machine)." -ForegroundColor Gray
  }
} else {
  Write-Host "[2] Skipping payment bot (-ApiOnly)." -ForegroundColor DarkYellow
}

Start-Sleep -Seconds 1

Write-Host "[3] Starting API (new window)..." -ForegroundColor Yellow
$cmdBackend = 'cd /d "' + $backendDir + '" && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-exclude scripts --reload-delay 1'
Start-TbccCmdWindow -Title "TBCC-Backend" -Command $cmdBackend

Write-Host "  Waiting for http://127.0.0.1:8000/health ..." -ForegroundColor Gray
Start-Sleep -Seconds 2
$backendUp = $false
for ($i = 0; $i -lt 30; $i++) {
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    if ($r.StatusCode -eq 200) { $backendUp = $true; break }
  } catch {}
  Start-Sleep -Seconds 1
}
if ($backendUp) {
  Write-Host "  API is up." -ForegroundColor Green
} else {
  Write-Host "  API not responding yet — check the TBCC-Backend window for errors." -ForegroundColor Yellow
}

if (-not $apiOnly) {
  Write-Host "[4] Starting payment bot (new window)..." -ForegroundColor Yellow
  $cmdPay = 'cd /d "' + $backendDir + '" && python -m bots.payment_bot'
  Start-TbccCmdWindow -Title "TBCC-PaymentBot" -Command $cmdPay
  Write-Host "  Payment bot window opened." -ForegroundColor Green
}

Write-Host ""
Write-Host "Done. Ensure tbcc/.env is saved before restart (TBCC_PROMO_PUBLIC_BASE_URL, TBCC_API_URL, etc.)." -ForegroundColor Gray
Write-Host ""
