# Sync TBCC secrets + Telethon sessions from home Windows PC to GCP VPS.
#
# Usage (after bootstrap + SSH works):
#   .\scripts\gcp\sync-stack-to-gcp.ps1 -RemoteHost tbcc-lean -RemoteUser ubuntu -UseGcloudSsh
#   .\scripts\gcp\sync-stack-to-gcp.ps1 -RemoteHost 34.x.x.x -RemoteUser ubuntu
#
# -UseGcloudSsh: use `gcloud compute ssh` instead of plain ssh (IAP-friendly)
# -EnvOnly: skip session files (secrets template only)
# -IncludeDbDump: pg_dump from home Postgres and restore on VPS (advanced migration)

param(
  [Parameter(Mandatory = $true)][string]$RemoteHost,
  [string]$RemoteUser = "ubuntu",
  [string]$RemoteTbccPath = "/opt/tbcc",
  [string]$GcpZone = "us-west1-b",
  [string]$GcpProject = "",
  [switch]$UseGcloudSsh,
  [switch]$EnvOnly,
  [switch]$IncludeDbDump
)

$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$backend = Join-Path $tbccRoot "backend"
$infra = Join-Path $tbccRoot "infra"
$localEnv = Join-Path $tbccRoot ".env"

function Invoke-Remote {
  param([string]$RemoteCmd)
  if ($UseGcloudSsh) {
    $proj = $GcpProject
    if (-not $proj) { $proj = (gcloud config get-value project 2>$null) }
    gcloud compute ssh $RemoteHost --zone=$GcpZone --project=$proj --command=$RemoteCmd
  } else {
    ssh "${RemoteUser}@${RemoteHost}" $RemoteCmd
  }
}

function Copy-ToRemote {
  param([string]$LocalPath, [string]$RemoteDest)
  if ($UseGcloudSsh) {
    $proj = $GcpProject
    if (-not $proj) { $proj = (gcloud config get-value project 2>$null) }
    gcloud compute scp $LocalPath "${RemoteUser}@${RemoteHost}:${RemoteDest}" --zone=$GcpZone --project=$proj
  } else {
    scp -p $LocalPath "${RemoteUser}@${RemoteHost}:${RemoteDest}"
  }
}

$remoteInfra = "$RemoteTbccPath/tbcc/infra"
if (-not (Test-Path (Join-Path $RemoteTbccPath "tbcc"))) {
  $remoteInfra = "$RemoteTbccPath/infra"
}

Write-Host "Creating remote dirs..."
Invoke-Remote "mkdir -p $remoteInfra/data/sessions $remoteInfra/data/media"

# Build GCP env from local .env + template keys
$template = Join-Path $infra "env.gcp-lean.example"
$gcpEnv = Join-Path $env:TEMP "tbcc-gcp-lean.env"
$lines = Get-Content $template -ErrorAction Stop
$local = @{}
if (Test-Path $localEnv) {
  Get-Content $localEnv | ForEach-Object {
    $t = $_.Trim()
    if (-not $t -or $t.StartsWith("#") -or $t -notmatch "=") { return }
    $k, $v = $t -split "=", 2
    $local[$k.Trim()] = $v.Trim().Trim('"').Trim("'")
  }
}
$out = New-Object System.Collections.ArrayList
foreach ($line in $lines) {
  if ($line -match '^([A-Z0-9_]+)=(.*)$' -and $local.ContainsKey($Matches[1])) {
    $key = $Matches[1]
    # Skip Windows-only / sqlite defaults
    if ($key -eq "DATABASE_URL" -and $local[$key] -match "sqlite") { [void]$out.Add($line); continue }
    if ($key -in @("TELEGRAM_SESSION_PATH", "TBCC_POSTER_TELEGRAM_SESSION", "TBCC_IMPORT_TELEGRAM_SESSION", "TBCC_ALBUM_COMPOSER_TELEGRAM_SESSION", "TBCC_SCRAPER_TELEGRAM_SESSION")) { continue }
    [void]$out.Add("$key=$($local[$key])")
  } else {
    [void]$out.Add($line)
  }
}
# Force Docker-internal URLs
$pgPass = if ($local["POSTGRES_PASSWORD"]) { $local["POSTGRES_PASSWORD"] } else { "CHANGE_ME_POSTGRES_PASSWORD" }
$filtered = $out | Where-Object { $_ -notmatch '^DATABASE_URL=' -and $_ -notmatch '^REDIS_URL=' -and $_ -notmatch '^POSTGRES_PASSWORD=' -and $_ -notmatch '^TBCC_API_URL=' }
$final = @(
  "DATABASE_URL=postgresql://postgres:${pgPass}@postgres:5432/tbcc"
  "REDIS_URL=redis://redis:6379/0"
  "POSTGRES_PASSWORD=$pgPass"
  "TBCC_API_URL=http://api:8000"
  "TBCC_STACK_PROFILE=lean"
  "TBCC_BOT_RUNTIME_ADAPTER=command"
) + $filtered
$final | Set-Content -Encoding utf8 $gcpEnv

Write-Host "Uploading .env.gcp-lean..."
Copy-ToRemote $gcpEnv "$remoteInfra/.env.gcp-lean"

if (-not $EnvOnly) {
  $sessionNames = @(
    "admin.session", "admin.session-wal", "admin.session-shm",
    "admin_poster.session", "admin_poster.session-wal", "admin_poster.session-shm",
    "admin_import.session", "admin_import.session-wal", "admin_import.session-shm",
    "admin_album.session", "admin_album.session-wal", "admin_album.session-shm",
    "scraper.session", "scraper.session-wal", "scraper.session-shm"
  )
  foreach ($name in $sessionNames) {
    $local = Join-Path $backend $name
    if (-not (Test-Path -LiteralPath $local)) {
      if ($name -match '\.(wal|shm)$') { continue }
      Write-Warning "Missing $local"
      continue
    }
    Write-Host "Copying $name ..."
    Copy-ToRemote $local "$remoteInfra/data/sessions/"
  }
}

Write-Host ""
Write-Host "Done. On the VM:" -ForegroundColor Green
Write-Host "  bash $RemoteTbccPath/tbcc/scripts/gcp/install-gcp-lean-stack.sh"
Write-Host "  # or if repo root is tbcc/: bash $RemoteTbccPath/scripts/gcp/install-gcp-lean-stack.sh"
