# Copy home Telethon admin.session onto the revenue island (loot Saved-Messages media).
# ONE host only - stop home backend/celery that use admin.session before copying.
#
#   .\scripts\revenue-island\sync-admin-session.ps1 -HostName root@5.161.53.91

param(
  [Parameter(Mandatory = $true)][string]$HostName,
  [string]$BackendDir = ""
)

$ErrorActionPreference = "Stop"
$tbccRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $BackendDir) { $BackendDir = Join-Path $tbccRoot "backend" }

$session = Join-Path $BackendDir "admin.session"
if (-not (Test-Path -LiteralPath $session)) {
  throw "Missing $session - log in on home first (python scripts/login_telethon_sessions.py)."
}

Write-Host "Hard rule: only the island may use this session after copy." -ForegroundColor Yellow
Write-Host "Confirm home TBCC-Backend / Celery / anything on admin.session is STOPPED." -ForegroundColor Yellow

$remoteDir = "/opt/tbcc/sessions"
& ssh $HostName "mkdir -p $remoteDir; chmod 700 $remoteDir"

$files = @(
  "admin.session",
  "admin.session-wal",
  "admin.session-shm"
)
foreach ($name in $files) {
  $local = Join-Path $BackendDir $name
  if (-not (Test-Path -LiteralPath $local)) { continue }
  Write-Host "scp $name" -ForegroundColor DarkGray
  & scp $local "${HostName}:$remoteDir/$name"
  if ($LASTEXITCODE -ne 0) { throw "scp failed for $name" }
}

& ssh $HostName "chmod 600 $remoteDir/admin.session* ; ls -la $remoteDir"

Write-Host "Next: recreate api+worker+worker_telegram+worker_post so they mount /sessions" -ForegroundColor Cyan
Write-Host ("  ssh {0} ""cd /opt/tbcc/infra; docker compose -f docker-compose.revenue-island.yml --env-file .env.revenue-island up -d --force-recreate api worker worker_telegram worker_post""" -f $HostName)
