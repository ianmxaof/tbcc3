# Full Storage Hub → AOF Forum drain (island API + R2 from tbcc/.env).
# Tuned: batch 20, 1500ms item delay. Cursor resumes; use --reset-cursor to restart.
$ErrorActionPreference = "Stop"
function Get-EnvVal($path, $key) {
  $line = Get-Content $path | Where-Object { $_ -match "^$key=" } | Select-Object -First 1
  if ($line) { return ($line -replace "^$key=", "").Trim() }
  return ""
}

$forumRoot = Split-Path $PSScriptRoot -Parent
$tbccEnv = Join-Path (Split-Path $forumRoot -Parent) "tbcc\.env"
if (-not (Test-Path $tbccEnv)) {
  throw "Missing tbcc .env at $tbccEnv"
}

$env:TBCC_API_URL = if ($env:TBCC_API_URL) { $env:TBCC_API_URL } else { "https://api.powercore.app" }
$env:TBCC_INTERNAL_API_KEY = Get-EnvVal $tbccEnv "TBCC_INTERNAL_API_KEY"
$env:TBCC_EXPORT_BATCH_LIMIT = "20"
$env:TBCC_EXPORT_ITEM_DELAY_MS = "1500"
# Full drain — do not cap batches
Remove-Item Env:TBCC_INGEST_MAX_BATCHES -ErrorAction SilentlyContinue
$env:B2_ENDPOINT = Get-EnvVal $tbccEnv "TBCC_R2_S3_ENDPOINT"
$env:B2_BUCKET = Get-EnvVal $tbccEnv "TBCC_R2_BUCKET"
$env:B2_KEY_ID = Get-EnvVal $tbccEnv "TBCC_R2_ACCESS_KEY_ID"
$env:B2_APP_KEY = Get-EnvVal $tbccEnv "TBCC_R2_SECRET_ACCESS_KEY"
$env:B2_REGION = "auto"
$env:NODE_OPTIONS = "--conditions=node"

$logDir = Join-Path $forumRoot ".tmp"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "storage-hub-drain.log"
Write-Host "Logging to $log"
Write-Host "TBCC_API_URL=$($env:TBCC_API_URL) batch=$($env:TBCC_EXPORT_BATCH_LIMIT) delayMs=$($env:TBCC_EXPORT_ITEM_DELAY_MS)"

Set-Location $forumRoot
$extra = @()
if ($args -contains "--reset-cursor") { $extra += "--reset-cursor" }
& npx tsx scripts/ingest-storage-hub.ts @extra 2>&1 | Tee-Object -FilePath $log -Append
