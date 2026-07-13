# Copy remote-worker GHCR scripts to VM (no git pull required).
#
# Usage:
#   .\scripts\remote-worker\sync-remote-worker-scripts.ps1 -ViaGcloud
#
param(
  [switch]$ViaGcloud,
  [string]$RemoteHost = "",
  [string]$RemoteUser = "ianm_powercore_gmail_com",
  [string]$RemotePath = "/opt/tbcc",
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

if (-not $RemoteHost) { $RemoteHost = Get-EnvVal "TBCC_REMOTE_STACK_HOST" }
$u = Get-EnvVal "TBCC_REMOTE_STACK_USER"; if ($u) { $RemoteUser = $u }
$p = Get-EnvVal "TBCC_REMOTE_STACK_PATH"; if ($p) { $RemotePath = $p }

$files = @(
  @{ Local = "infra\docker-compose.remote-worker.ghcr.yml"; Remote = "$RemotePath/infra/docker-compose.remote-worker.ghcr.yml" },
  @{ Local = "scripts\remote-worker\pull-remote-worker.sh"; Remote = "$RemotePath/scripts/remote-worker/pull-remote-worker.sh" },
  @{ Local = "scripts\remote-worker\install-remote-worker.sh"; Remote = "$RemotePath/scripts/remote-worker/install-remote-worker.sh" },
  @{ Local = "scripts\remote-worker\health-remote-worker.sh"; Remote = "$RemotePath/scripts/remote-worker/health-remote-worker.sh" }
)

foreach ($f in $files) {
  $localPath = Join-Path $tbccRoot $f.Local
  if (-not (Test-Path -LiteralPath $localPath)) {
    throw "Missing local file: $localPath"
  }
}

if ($ViaGcloud) {
  if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) { throw "gcloud not found" }
  $mkdir = "mkdir -p $RemotePath/infra $RemotePath/scripts/remote-worker"
  & gcloud compute ssh $InstanceName --zone=$Zone --project=$ProjectId --tunnel-through-iap --command=$mkdir | Out-Null
  foreach ($f in $files) {
    $localPath = Join-Path $tbccRoot $f.Local
    Write-Host "  scp $(Split-Path $f.Local -Leaf) -> VM" -ForegroundColor Gray
    & gcloud compute scp $localPath "${InstanceName}:$($f.Remote)" --zone=$Zone --project=$ProjectId --tunnel-through-iap
    if ($LASTEXITCODE -ne 0) { throw "gcloud scp failed for $($f.Local)" }
  }
  $chmod = "chmod +x $RemotePath/scripts/remote-worker/*.sh"
  & gcloud compute ssh $InstanceName --zone=$Zone --project=$ProjectId --tunnel-through-iap --command=$chmod | Out-Null
} else {
  if (-not $RemoteHost) { throw "Pass -RemoteHost or set TBCC_REMOTE_STACK_HOST" }
  ssh "${RemoteUser}@${RemoteHost}" "mkdir -p $RemotePath/infra $RemotePath/scripts/remote-worker"
  foreach ($f in $files) {
    $localPath = Join-Path $tbccRoot $f.Local
    scp -p $localPath "${RemoteUser}@${RemoteHost}:$($f.Remote)"
  }
  ssh "${RemoteUser}@${RemoteHost}" "chmod +x $RemotePath/scripts/remote-worker/*.sh"
}

Write-Host "Remote worker scripts synced." -ForegroundColor Green
