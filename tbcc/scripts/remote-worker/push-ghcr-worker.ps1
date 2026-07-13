# Push TBCC backend image to GHCR from this PC (or use GitHub Actions).
#
# Prerequisites:
#   - Docker Desktop running
#   - GitHub PAT with write:packages (or use `gh auth token`)
#   - Optional in tbcc/.env: TBCC_GHCR_USER, TBCC_GHCR_TOKEN
#
# Usage:
#   cd tbcc
#   .\scripts\remote-worker\push-ghcr-worker.ps1
#   .\scripts\remote-worker\push-ghcr-worker.ps1 -Tag "lean-stack-hardening"
#
param(
  [string]$Image = "ghcr.io/ianmxaof/tbcc-worker",
  [string]$Tag = "latest",
  [string]$ExtraTag = "",
  [switch]$NoPush
)

$ErrorActionPreference = "Stop"
$tbccRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$backend = Join-Path $tbccRoot "backend"
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

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "docker not found. Start Docker Desktop or install Docker."
}

$user = Get-EnvVal "TBCC_GHCR_USER"
if (-not $user) { $user = Get-EnvVal "TBCC_GITHUB_USER" }
if (-not $user) { $user = "ianmxaof" }

$token = Get-EnvVal "TBCC_GHCR_TOKEN"
if (-not $token) {
  try {
    $token = (& gh auth token 2>$null)
    if ($token) { $token = $token.Trim() }
  } catch { }
}
if (-not $token) {
  throw "Set TBCC_GHCR_TOKEN in tbcc/.env (PAT with write:packages) or run: gh auth login"
}

$full = "${Image}:${Tag}"
Write-Host "Building $full from $backend ..." -ForegroundColor Cyan
Push-Location $backend
try {
  docker build -t $full .
  if ($LASTEXITCODE -ne 0) { throw "docker build failed" }
  if ($ExtraTag) {
    docker tag $full "${Image}:${ExtraTag}"
  }
} finally {
  Pop-Location
}

if ($NoPush) {
  Write-Host "Built locally (no push): $full" -ForegroundColor Green
  exit 0
}

Write-Host "Logging into ghcr.io as $user ..." -ForegroundColor Yellow
$token | docker login ghcr.io -u $user --password-stdin
if ($LASTEXITCODE -ne 0) { throw "docker login ghcr.io failed" }

Write-Host "Pushing $full ..." -ForegroundColor Yellow
docker push $full
if ($LASTEXITCODE -ne 0) { throw "docker push failed" }
if ($ExtraTag) {
  docker push "${Image}:${ExtraTag}"
}

Write-Host ""
Write-Host "OK. On the VM:" -ForegroundColor Green
Write-Host "  export TBCC_WORKER_IMAGE=$full"
Write-Host "  export TBCC_USE_GHCR=1"
Write-Host "  bash /opt/tbcc/scripts/remote-worker/pull-remote-worker.sh"
Write-Host ""
Write-Host 'Or from home: .\scripts\remote-worker\update-remote-worker.ps1 -RemoteHost 100.x.y.z'
