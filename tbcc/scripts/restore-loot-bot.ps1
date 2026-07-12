# Restore TBCC-LootBot: clear stale dashboard token override, migrate DB, kill strays, restart once.
param(
  [string]$TbccRoot = (Split-Path $PSScriptRoot -Parent)
)

$ErrorActionPreference = "Stop"
$backend = Join-Path $TbccRoot "backend"
$envFile = Join-Path $TbccRoot ".env"
$cli = Join-Path $TbccRoot "scripts\tbcc-stack-cli.ps1"
$kill = Join-Path $TbccRoot "scripts\tbcc-kill-stray-processes.ps1"

Write-Host "TBCC LootBot restore" -ForegroundColor Cyan

# Docker infra
$infra = Join-Path $TbccRoot "infra"
Push-Location $infra
try {
  cmd /c "docker compose -f docker-compose.infra.yml up -d postgres redis"
} finally { Pop-Location }

Start-Sleep -Seconds 5

Push-Location $backend
try {
  py -3.13 -m alembic upgrade head
} finally { Pop-Location }

# Clear dashboard token override so .env token wins (empty string clears per API)
$dot = Get-Content $envFile -Raw
if ($dot -match 'TBCC_INTERNAL_API_KEY=(\S+)') {
  $key = $Matches[1].Trim()
  try {
    $body = '{"bot_token":""}'
    Invoke-RestMethod -Uri "http://127.0.0.1:8000/loot-bot-settings" -Method PATCH `
      -Headers @{ "X-TBCC-Internal-Key" = $key; "Content-Type" = "application/json" } `
      -Body $body -TimeoutSec 30
    Write-Host "Cleared dashboard loot token override (using .env)." -ForegroundColor Green
  } catch {
    Write-Host "Could not PATCH loot-bot-settings (backend may need restart): $($_.Exception.Message)" -ForegroundColor Yellow
  }
}

if (Test-Path $kill) {
  # Kill only duplicate loot_bot PIDs (keep one tray instance).
  $lootProcs = @(Get-CimInstance Win32_Process -Filter "name='python.exe'" | Where-Object { $_.CommandLine -like '*bots.loot_bot*' })
  if ($lootProcs.Count -gt 1) {
    $lootProcs | Sort-Object ProcessId -Descending | Select-Object -Skip 1 | ForEach-Object {
      Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Stopped $($lootProcs.Count - 1) duplicate loot_bot process(es)." -ForegroundColor Yellow
  }
}

& powershell -NoProfile -ExecutionPolicy Bypass -File $cli -Action Restart -Service loot
Start-Sleep -Seconds 8
& powershell -NoProfile -ExecutionPolicy Bypass -File $cli -Action Status | ConvertFrom-Json | Select-Object -ExpandProperty services | Where-Object { $_.id -eq "loot" }

$procs = Get-CimInstance Win32_Process -Filter "name='python.exe'" | Where-Object { $_.CommandLine -like '*bots.loot_bot*' }
Write-Host ("loot_bot python processes: " + @($procs).Count) -ForegroundColor $(if (@($procs).Count -le 1) { "Green" } else { "Yellow" })
