# One-batch smoke — loads TBCC .env for keys; not for routine use.
$ErrorActionPreference = "Stop"
function Get-EnvVal($path, $key) {
  $line = Get-Content $path | Where-Object { $_ -match "^$key=" } | Select-Object -First 1
  if ($line) { return ($line -replace "^$key=", "").Trim() }
  return ""
}

$tbccEnv = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) "tbcc\.env"
$env:TBCC_API_URL = "https://api.powercore.app"
$env:TBCC_INTERNAL_API_KEY = Get-EnvVal $tbccEnv "TBCC_INTERNAL_API_KEY"
$env:TBCC_EXPORT_BATCH_LIMIT = "2"
$env:TBCC_EXPORT_ITEM_DELAY_MS = "1500"
$env:TBCC_INGEST_MAX_BATCHES = "1"
$env:B2_ENDPOINT = Get-EnvVal $tbccEnv "TBCC_R2_S3_ENDPOINT"
$env:B2_BUCKET = Get-EnvVal $tbccEnv "TBCC_R2_BUCKET"
$env:B2_KEY_ID = Get-EnvVal $tbccEnv "TBCC_R2_ACCESS_KEY_ID"
$env:B2_APP_KEY = Get-EnvVal $tbccEnv "TBCC_R2_SECRET_ACCESS_KEY"
$env:B2_REGION = "auto"

Set-Location (Split-Path $PSScriptRoot -Parent)
$env:NODE_OPTIONS = "--conditions=node"
npx tsx scripts/ingest-storage-hub.ts
