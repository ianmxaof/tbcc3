# Hot-patch Python files onto the revenue island AND always restart affected containers.
# Never docker-cp into a running container without restart — code stays invisible until recycle.
#
#   .\scripts\revenue-island\hot-patch-island.ps1 -RelativePaths @("app/services/gatekeeper_review.py")
#   .\scripts\revenue-island\hot-patch-island.ps1 -RelativePaths @("app/services/foo.py") -Services api,worker
#
# Prefer full deploy for anything non-trivial:
#   .\scripts\revenue-island\deploy-island-live.ps1

param(
  [string]$HostName = "root@5.161.53.91",
  [string]$RemoteDir = "/opt/tbcc",
  [Parameter(Mandatory = $true)]
  [string[]]$RelativePaths,
  [string[]]$Services = @("api", "worker", "worker_telegram", "worker_post"),
  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$tbccRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$backend = Join-Path $tbccRoot "backend"
$composeFile = "docker-compose.revenue-island.yml"
$envFile = ".env.revenue-island"

if (-not $RelativePaths -or $RelativePaths.Count -eq 0) {
  throw "Pass -RelativePaths (paths under tbcc/backend, e.g. app/services/foo.py)"
}

function Invoke-Remote([string]$cmd) {
  if ($WhatIf) { Write-Host "WHATIF ssh $HostName $cmd" -ForegroundColor DarkGray; return "" }
  $prev = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $out = (& ssh $HostName $cmd 2>&1 | Out-String).TrimEnd()
  $ErrorActionPreference = $prev
  if ($LASTEXITCODE -ne 0) { throw "Remote command failed (exit $LASTEXITCODE): $cmd`n$out" }
  return $out
}

Write-Host "=== TBCC island hot-patch (copy + mandatory restart) ===" -ForegroundColor Cyan
Write-Host "Prefer deploy-island-live.ps1 for multi-file / image changes." -ForegroundColor DarkGray

$copied = 0
foreach ($rel in $RelativePaths) {
  $norm = ($rel -replace '\\', '/').TrimStart('/')
  if ($norm.StartsWith("backend/")) { $norm = $norm.Substring("backend/".Length) }
  $local = Join-Path $backend ($norm -replace '/', [IO.Path]::DirectorySeparatorChar)
  if (-not (Test-Path -LiteralPath $local)) {
    throw "Local file missing: $local"
  }
  $remoteBackendSrc = "$RemoteDir/backend-src/$norm"
  $remoteDirOnly = Split-Path $remoteBackendSrc -Parent
  Write-Host "scp $norm -> island backend-src" -ForegroundColor Yellow
  if ($WhatIf) {
    Write-Host "WHATIF scp $local ${HostName}:$remoteBackendSrc" -ForegroundColor DarkGray
  } else {
    Invoke-Remote "mkdir -p $remoteDirOnly"
    & scp $local "${HostName}:$remoteBackendSrc"
    if ($LASTEXITCODE -ne 0) { throw "scp failed for $norm" }
  }
  $copied++

  # Also docker cp into running containers so the next restart/process reload sees files
  # even when the image layer is stale — restart below is still mandatory.
  foreach ($svc in $Services) {
    $cidCmd = "cd $RemoteDir/infra && docker compose -f $composeFile --env-file $envFile ps -q $svc"
    if ($WhatIf) {
      Write-Host "WHATIF docker cp into $svc:/app/$norm" -ForegroundColor DarkGray
      continue
    }
    $cid = (Invoke-Remote $cidCmd).Trim()
    if (-not $cid) {
      Write-Host "WARN: no container for service $svc — skip docker cp" -ForegroundColor Yellow
      continue
    }
    $containerPath = "/app/$norm"
    $containerDir = Split-Path $containerPath -Parent
    Invoke-Remote "docker exec $cid mkdir -p $containerDir"
    & scp $local "${HostName}:/tmp/tbcc-hotpatch-file"
    Invoke-Remote "docker cp /tmp/tbcc-hotpatch-file ${cid}:$containerPath && rm -f /tmp/tbcc-hotpatch-file"
    Write-Host "  docker cp -> $svc:$containerPath" -ForegroundColor DarkGray
  }
}

if ($copied -lt 1) { throw "Nothing copied" }

$svcList = ($Services -join " ")
Write-Host "`nRestarting services (required — without this, patches are invisible): $svcList" -ForegroundColor Yellow
if ($WhatIf) {
  Write-Host "WHATIF compose restart $svcList" -ForegroundColor DarkGray
} else {
  Invoke-Remote "cd $RemoteDir/infra && docker compose -f $composeFile --env-file $envFile restart $svcList"
  $started = Invoke-Remote "cd $RemoteDir/infra && docker compose -f $composeFile --env-file $envFile ps --format '{{.Service}} {{.Status}}' $svcList"
  Write-Host $started
  $health = Invoke-Remote "curl -fsS --max-time 8 http://127.0.0.1:8000/health || true"
  Write-Host "health: $health" -ForegroundColor Green
}

Write-Host "`n=== Hot-patch complete (copied=$copied, restarted) ===" -ForegroundColor Green
Write-Host "Evidence: compose ps Status should show recent Up; /health must respond."
Write-Host "DO NOT raw 'docker cp' without this script or a compose restart/recreate."
