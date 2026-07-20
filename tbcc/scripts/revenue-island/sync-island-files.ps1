# Copy revenue-island compose + env template (+ scripts) to the VPS over SCP.
# Does not start containers or bots.
#
#   .\scripts\revenue-island\sync-island-files.ps1 -HostName root@203.0.113.10
#   .\scripts\revenue-island\sync-island-files.ps1 -HostName root@tbcc-revenue-island  # Tailscale MagicDNS

param(
  [Parameter(Mandatory = $true)][string]$HostName,
  [string]$RemoteDir = "/opt/tbcc",
  [switch]$IncludeFilledEnv,
  [string]$LocalEnvFile = ""
)

$ErrorActionPreference = "Stop"
$tbccRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$infra = Join-Path $tbccRoot "infra"
$scripts = Join-Path $tbccRoot "scripts\revenue-island"
$docs = Join-Path $tbccRoot "docs\REVENUE_ISLAND.md"

$ssh = Get-Command ssh -ErrorAction SilentlyContinue
$scp = Get-Command scp -ErrorAction SilentlyContinue
if (-not $ssh -or -not $scp) {
  throw "OpenSSH client (ssh/scp) required. Enable optional feature or install via Settings -> Apps -> Optional features."
}

Write-Host "mkdir $RemoteDir on $HostName ..." -ForegroundColor DarkCyan
& ssh $HostName "mkdir -p $RemoteDir/infra $RemoteDir/scripts/revenue-island $RemoteDir/docs"

$files = @(
  @{ Local = (Join-Path $infra "docker-compose.revenue-island.yml"); Remote = "$RemoteDir/infra/" },
  @{ Local = (Join-Path $infra "env.revenue-island.example"); Remote = "$RemoteDir/infra/" },
  @{ Local = (Join-Path $scripts "bootstrap-island.sh"); Remote = "$RemoteDir/scripts/revenue-island/" },
  @{ Local = (Join-Path $scripts "up-island-bots.sh"); Remote = "$RemoteDir/scripts/revenue-island/" },
  @{ Local = (Join-Path $scripts "install-island-api-tunnel.sh"); Remote = "$RemoteDir/scripts/revenue-island/" },
  @{ Local = (Join-Path $scripts "install-island-named-tunnel.sh"); Remote = "$RemoteDir/scripts/revenue-island/" },
  @{ Local = (Join-Path $scripts "wire-island-webhooks.ps1"); Remote = "$RemoteDir/scripts/revenue-island/" },
  @{ Local = (Join-Path $scripts "deploy-island-live.ps1"); Remote = "$RemoteDir/scripts/revenue-island/" },
  @{ Local = $docs; Remote = "$RemoteDir/docs/" }
)

foreach ($f in $files) {
  if (-not (Test-Path -LiteralPath $f.Local)) { throw "Missing $($f.Local)" }
  Write-Host ("scp {0}" -f (Split-Path $f.Local -Leaf)) -ForegroundColor DarkGray
  & scp $f.Local "${HostName}:$($f.Remote)"
  if ($LASTEXITCODE -ne 0) { throw "scp failed for $($f.Local)" }
}

& ssh $HostName "chmod +x $RemoteDir/scripts/revenue-island/*.sh; sed -i 's/\r$//' $RemoteDir/scripts/revenue-island/*.sh 2>/dev/null || true"

if ($IncludeFilledEnv) {
  $envPath = if ($LocalEnvFile) { $LocalEnvFile } else { Join-Path $infra ".env.revenue-island" }
  if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Missing $envPath - copy from env.revenue-island.example and fill secrets first."
  }
  Write-Host "scp filled .env.revenue-island (secrets - keep off git)" -ForegroundColor Yellow
  & scp $envPath "${HostName}:$RemoteDir/infra/.env.revenue-island"
  if ($LASTEXITCODE -ne 0) { throw "scp failed for filled .env.revenue-island" }
}

Write-Host "Synced. On the VPS:" -ForegroundColor Green
Write-Host "  cp $RemoteDir/infra/env.revenue-island.example $RemoteDir/infra/.env.revenue-island   # if needed" -ForegroundColor DarkGray
Write-Host "  nano $RemoteDir/infra/.env.revenue-island   # fill BOT_TOKEN / R2 / etc." -ForegroundColor DarkGray
Write-Host "  bash $RemoteDir/scripts/revenue-island/bootstrap-island.sh" -ForegroundColor DarkGray
