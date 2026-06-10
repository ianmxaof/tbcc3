# Purge stale Celery broker queues (Redis). Use when scheduled posts stop but Beat shows running.
param(
  [string]$TbccRoot = "",
  [string[]]$Queues = @("celery", "post"),
  [switch]$Force
)

$ErrorActionPreference = "Stop"
if (-not $TbccRoot) { $TbccRoot = Split-Path $PSScriptRoot -Parent }
$backend = Join-Path $TbccRoot "backend"
$py = "py -3.13"
try {
  $p313 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"
  if (Test-Path -LiteralPath $p313) { $py = "`"$p313`"" }
} catch {}

$qJson = ($Queues | ConvertTo-Json -Compress)
if (-not $Force) {
  Write-Host "This deletes pending Celery tasks in Redis queues: $($Queues -join ', ')" -ForegroundColor Yellow
  Write-Host "Run with -Force after stopping TBCC-Celery / TBCC-Celery-Post tabs (or whole stack)." -ForegroundColor Gray
  $confirm = Read-Host "Type PURGE to continue"
  if ($confirm -ne "PURGE") { Write-Host "Cancelled."; exit 0 }
}

$code = @"
import json, os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(r'$TbccRoot') / '.env')
from app.services.celery_queue_ops import celery_queue_snapshot, purge_celery_queues
before = celery_queue_snapshot()
queues = json.loads(r'''$qJson''')
after = purge_celery_queues(queues, min_length=0)
print(json.dumps({'before': before, 'purge': after}, indent=2))
"@
Set-Location $backend
Invoke-Expression "$py -c $([char]34 + ($code -replace '"','\"') + [char]34)"
