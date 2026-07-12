# SSH to remote worker and pull latest GHCR image (no on-VM build).
#
# Usage:
#   .\scripts\remote-worker\update-remote-worker.ps1 -RemoteHost 100.x.y.z
#   .\scripts\remote-worker\update-remote-worker.ps1 -RemoteHost 100.x.y.z -ViaGcloud
#
param(
  [string]$RemoteHost = "",
  [string]$RemoteUser = "ubuntu",
  [string]$RemotePath = "/opt/tbcc",
  [string]$Image = "ghcr.io/ianmxaof/tbcc-worker:latest",
  [switch]$ViaGcloud,
  [string]$ProjectId = "tbcc-cloud-instance",
  [string]$Zone = "us-west1-a",
  [string]$InstanceName = "tbcc-remote-worker"
)

$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$envFile = Join-Path $tbccRoot ".env"

function Get-EnvVal([string]$Name) {
  if (-not (Test-Path -LiteralPath $envFile)) { return "" }
  foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
    if ($line -match "^\s*$([regex]::Escape($Name))\s*=\s*(.*)$") {
      return $Matches[1].Trim().Trim('"').Trim("'")
    }
  }
  return ""
}

if (-not $RemoteHost) {
  $RemoteHost = Get-EnvVal "TBCC_REMOTE_STACK_HOST"
}
$userFromEnv = Get-EnvVal "TBCC_REMOTE_STACK_USER"
if ($userFromEnv) { $RemoteUser = $userFromEnv }
$pathFromEnv = Get-EnvVal "TBCC_REMOTE_STACK_PATH"
if ($pathFromEnv) { $RemotePath = $pathFromEnv }

$ghcrUser = Get-EnvVal "TBCC_GHCR_USER"
if (-not $ghcrUser) { $ghcrUser = "ianmxaof" }
$ghcrToken = Get-EnvVal "TBCC_GHCR_TOKEN"

# Single-line remote command — multiline bash breaks through gcloud/PowerShell quoting.
$pullScript = "scripts/remote-worker/pull-remote-worker.sh"
$remoteCmd = @(
  "cd '$RemotePath'",
  "TBCC_USE_GHCR=1 TBCC_WORKER_IMAGE='$Image' TBCC_GHCR_USER='$ghcrUser' TBCC_GHCR_TOKEN='$ghcrToken'",
  "if test -f '$pullScript'; then bash '$pullScript'; else cd infra && docker compose -f docker-compose.remote-worker.ghcr.yml pull && docker compose -f docker-compose.remote-worker.ghcr.yml up -d --force-recreate; fi"
) -join " && "

Write-Host "Updating remote worker image to $Image ..." -ForegroundColor Cyan

if ($ViaGcloud) {
  if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud not found"
  }
  & gcloud compute ssh $InstanceName --zone=$Zone --project=$ProjectId --tunnel-through-iap --command=$remoteCmd
} else {
  if (-not $RemoteHost) {
    throw "Pass -RemoteHost or set TBCC_REMOTE_STACK_HOST in .env"
  }
  ssh "${RemoteUser}@${RemoteHost}" $remoteCmd
}

if ($LASTEXITCODE -ne 0) { throw "Remote update failed (exit $LASTEXITCODE)" }
Write-Host "Remote worker updated." -ForegroundColor Green
