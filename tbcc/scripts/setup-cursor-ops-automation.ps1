# Enable + verify TBCC Cursor ops automation (tiers 1-5)
$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $tbccRoot "backend"
$py = if ($env:TBCC_PYTHON) { $env:TBCC_PYTHON } else { "py" }

Write-Host "=== TBCC Cursor ops automation setup ===" -ForegroundColor Cyan

# cursor-sdk for SDK triage bridge (non-blocking check)
Write-Host "`nChecking cursor-sdk..." -ForegroundColor Yellow
$sdkOk = $false
try {
    & $py -3.13 -c "import cursor_sdk" 2>&1 | Out-Null
    $sdkOk = ($LASTEXITCODE -eq 0)
}
catch {
    $sdkOk = $false
}
if (-not $sdkOk) {
    Write-Host "  Run: py -3.13 -m pip install cursor-sdk" -ForegroundColor DarkYellow
} else {
    Write-Host "  cursor-sdk installed" -ForegroundColor Green
}

# Health checks (backend must be running)
$base = if ($env:TBCC_API_BASE) { $env:TBCC_API_BASE } else { "http://127.0.0.1:8000" }
$endpoints = @(
    "/ops/triage/status",
    "/ops/flywheel/status",
    "/ops/focus"
)

Write-Host "`nProbing $base ..." -ForegroundColor Yellow
$ok = $true
foreach ($path in $endpoints) {
    try {
        $r = Invoke-RestMethod -Uri "$base$path" -Method GET -TimeoutSec 15
        Write-Host "  OK $path" -ForegroundColor Green
        if ($path -eq "/ops/triage/status") {
            Write-Host "    enabled=$($r.enabled) auto_fix=$($r.auto_fix) pr_only=$($r.pr_only)" -ForegroundColor DarkGray
        }
    }
    catch {
        Write-Host "  FAIL $path - $($_.Exception.Message)" -ForegroundColor Red
        $ok = $false
    }
}

if (-not $ok) {
    Write-Host "`nStart backend: tbcc\start.ps1 or supervisor tray, then re-run this script." -ForegroundColor Yellow
}

# CURSOR_API_KEY reminder
$envFile = Join-Path $tbccRoot ".env"
if (Test-Path $envFile) {
    $hasKey = Select-String -Path $envFile -Pattern '^\s*CURSOR_API_KEY=\S+' -Quiet
    if (-not $hasKey) {
        Write-Host "`nACTION: Set CURSOR_API_KEY in tbcc\.env (cursor.com/settings)" -ForegroundColor Magenta
    }
}

Write-Host "`n=== Cursor Automation (Tier 3) ===" -ForegroundColor Cyan
Write-Host "1. Cursor -> Automations -> New automation"
Write-Host "2. Name: TBCC critical ops triage"
Write-Host "3. Trigger: Manual, then cron every 15 min"
Write-Host "4. Repo: $tbccRoot"
Write-Host "5. Instructions: tbcc\docs\CURSOR_OPS_AUTOMATION.md"
Write-Host "6. Prefill JSON: tbcc\docs\automations\tbcc-ops-triage-prefill.json"
Write-Host "`nFlywheel tick (internal event bus): tbcc\scripts\run-tbcc-flywheel-tick.ps1" -ForegroundColor DarkGray
