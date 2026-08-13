# Smoke: retry a few failed hub jobs using tbcc/.env for island + R2.
$ErrorActionPreference = "Stop"
function Get-EnvVal($path, $key) {
  $line = Get-Content $path | Where-Object { $_ -match "^$key=" } | Select-Object -First 1
  if ($line) { return ($line -replace "^$key=", "").Trim() }
  return ""
}

$forumRoot = Split-Path $PSScriptRoot -Parent
$tbccEnv = Join-Path (Split-Path $forumRoot -Parent) "tbcc\.env"

$env:TBCC_API_URL = "https://api.powercore.app"
$env:TBCC_INTERNAL_API_KEY = Get-EnvVal $tbccEnv "TBCC_INTERNAL_API_KEY"
$env:B2_ENDPOINT = Get-EnvVal $tbccEnv "TBCC_R2_S3_ENDPOINT"
$env:B2_BUCKET = Get-EnvVal $tbccEnv "TBCC_R2_BUCKET"
$env:B2_KEY_ID = Get-EnvVal $tbccEnv "TBCC_R2_ACCESS_KEY_ID"
$env:B2_APP_KEY = Get-EnvVal $tbccEnv "TBCC_R2_SECRET_ACCESS_KEY"
$env:B2_REGION = "auto"
$env:NODE_OPTIONS = "--conditions=node"
$env:TBCC_DOWNLOAD_RETRIES = "2"

Set-Location $forumRoot
npx tsx scripts/retry-storage-hub-failed.ts --limit 3
