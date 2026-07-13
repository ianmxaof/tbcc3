# Sync scraper.session from home PC to remote TBCC worker VM.
#
# Usage:
#   .\scripts\remote-worker\sync-scraper-session.ps1 -RemoteHost 100.x.y.z -RemoteUser ianm_powercore_gmail_com
#   .\scripts\remote-worker\sync-scraper-session.ps1 -ViaGcloud -RemoteHost 100.x.y.z -RemoteUser ianm_powercore_gmail_com
#
param(
  [string]$RemoteHost = "",
  [string]$RemoteUser = "ianm_powercore_gmail_com",
  [string]$RemotePath = "/opt/tbcc/infra/data/sessions",
  [switch]$IncludePoster,
  [switch]$ViaGcloud,
  [string]$ProjectId = "tbcc-cloud-instance",
  [string]$Zone = "us-west1-a",
  [string]$InstanceName = "tbcc-remote-worker"
)

$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$backend = Join-Path $tbccRoot "backend"
$envFile = Join-Path $tbccRoot ".env"

if (-not $RemoteHost) {
  foreach ($line in (Get-Content -LiteralPath $envFile -Encoding UTF8 -ErrorAction SilentlyContinue)) {
    if ($line -match '^\s*TBCC_REMOTE_STACK_HOST\s*=\s*(.+)$') {
      $RemoteHost = $Matches[1].Trim().Trim('"')
      break
    }
  }
}
if (-not $RemoteHost) { throw "Pass -RemoteHost or set TBCC_REMOTE_STACK_HOST in .env" }

$files = @(
  "scraper.session",
  "scraper.session-wal",
  "scraper.session-shm"
)
if ($IncludePoster) {
  $files += @("admin_poster.session", "admin_poster.session-wal", "admin_poster.session-shm")
}

if ($ViaGcloud) {
  if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) { throw "gcloud not found" }
  & gcloud compute ssh $InstanceName --zone=$Zone --project=$ProjectId --tunnel-through-iap --command="mkdir -p $RemotePath" | Out-Null
  foreach ($name in $files) {
    $local = Join-Path $backend $name
    if (-not (Test-Path -LiteralPath $local)) {
      if ($name -match '\.(wal|shm)$') { continue }
      Write-Warning "Missing $local - run setup-scraper-session.ps1 on home PC first."
      continue
    }
    Write-Host "Copying $name (gcloud scp) ..."
    & gcloud compute scp $local "${InstanceName}:${RemotePath}/$name" --zone=$Zone --project=$ProjectId --tunnel-through-iap
  }
} else {
  $dest = "${RemoteUser}@${RemoteHost}:${RemotePath}/"
  Write-Host "Creating remote dir $RemotePath ..."
  ssh "${RemoteUser}@${RemoteHost}" "mkdir -p $RemotePath"
  foreach ($name in $files) {
    $local = Join-Path $backend $name
    if (-not (Test-Path -LiteralPath $local)) {
      if ($name -match '\.(wal|shm)$') { continue }
      Write-Warning "Missing $local - run setup-scraper-session.ps1 on home PC first."
      continue
    }
    Write-Host "Copying $name ..."
    scp -p $local $dest
  }
}

Write-Host ""
Write-Host "Done. Ensure worker on VM:" -ForegroundColor Green
Write-Host "  .\scripts\remote-worker\update-remote-worker.ps1 -ViaGcloud" -ForegroundColor Green
