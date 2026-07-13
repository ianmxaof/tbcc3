# Routine launch: Tailscale mesh + sync GHCR scripts + pull image + ensure worker up.
# Called from start.ps1 [0c] when TBCC_REMOTE_STACK_HOST is set.
#
# Usage:
#   .\scripts\remote-worker\launch-remote-worker.ps1
#   .\scripts\remote-worker\launch-remote-worker.ps1 -PushImage
#   .\scripts\remote-worker\launch-remote-worker.ps1 -Quiet
#
param(
  [switch]$Quiet,
  [switch]$EnsureWorker,
  [switch]$UseGhcr,
  [switch]$SkipGhcr,
  [switch]$PushImage,
  [switch]$SkipTailscale,
  [string]$ProjectId = "tbcc-cloud-instance",
  [string]$Zone = "us-west1-a",
  [string]$InstanceName = "tbcc-remote-worker"
)

$ErrorActionPreference = "Continue"
$here = $PSScriptRoot
$tbccRoot = Split-Path (Split-Path $here -Parent) -Parent
$envFile = Join-Path $tbccRoot ".env"

function Write-Rw([string]$msg, [string]$color = "Gray") {
  if (-not $Quiet) { Write-Host $msg -ForegroundColor $color }
}

function Get-EnvVal([string]$Name) {
  if (-not (Test-Path -LiteralPath $envFile)) { return "" }
  foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
    if ($line -match "^\s*$([regex]::Escape($Name))\s*=\s*(.*)$") {
      return $Matches[1].Trim().Trim('"').Trim("'")
    }
  }
  return ""
}

$remoteHost = Get-EnvVal "TBCC_REMOTE_STACK_HOST"
if (-not $remoteHost) {
  Write-Rw "Remote worker skipped (TBCC_REMOTE_STACK_HOST unset)." "DarkYellow"
  return @{ ok = $true; skipped = $true }
}

$useGhcrFlag = Get-EnvVal "TBCC_USE_GHCR"
$wantGhcr = $UseGhcr -or ($useGhcrFlag -eq "1") -or ($useGhcrFlag -eq "true")
if ($SkipGhcr) { $wantGhcr = $false }
if (-not $wantGhcr -and $EnsureWorker) { $wantGhcr = $true }  # default GHCR on stack launch

Write-Rw "[0c] Remote worker launch (VM $remoteHost)..." "Yellow"

if (-not $SkipTailscale) {
  $ensureTs = Join-Path $here "ensure-tailscale-home.ps1"
  if (Test-Path -LiteralPath $ensureTs) {
    . $ensureTs
    $ts = Ensure-TbccTailscaleMesh -RemoteHost $remoteHost
    if (-not $ts.ok) {
      Write-Rw "  Tailscale not ready - remote scrape may backlog." "Yellow"
    }
  }
}

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
  Write-Rw "  gcloud missing - cannot ensure remote worker." "Red"
  return @{ ok = $false; error = "gcloud_missing" }
}

$pushOnLaunch = Get-EnvVal "TBCC_GHCR_PUSH_ON_LAUNCH"
if ($PushImage -or ($pushOnLaunch -eq "1")) {
  Write-Rw "  Pushing GHCR worker image..." "Gray"
  try {
    & (Join-Path $here "push-ghcr-worker.ps1")
  } catch {
    Write-Rw "  GHCR push failed: $_ (continuing with existing image tag)" "Yellow"
  }
}

# Remote bash snippets use single-quoted PS strings so && / || stay literal.
$legacyCmd = 'cd /opt/tbcc/infra; docker compose -f docker-compose.remote-worker.yml up -d'
$checkCmd = @'
(docker compose -f /opt/tbcc/infra/docker-compose.remote-worker.ghcr.yml ps --status running -q worker_scrape 2>/dev/null) || (docker compose -f /opt/tbcc/infra/docker-compose.remote-worker.yml ps --status running -q worker_scrape)
'@

if ($wantGhcr) {
  Write-Rw "  Syncing GHCR compose/scripts to VM..." "Gray"
  try {
    & (Join-Path $here "sync-remote-worker-scripts.ps1") -ViaGcloud -ProjectId $ProjectId -Zone $Zone -InstanceName $InstanceName
  } catch {
    Write-Rw "  Script sync warning: $_" "Yellow"
  }
  Write-Rw "  Pulling GHCR image on VM..." "Gray"
  try {
    & (Join-Path $here "update-remote-worker.ps1") -ViaGcloud -ProjectId $ProjectId -Zone $Zone -InstanceName $InstanceName
  } catch {
    Write-Rw "  GHCR pull failed - trying legacy compose ensure..." "Yellow"
    & gcloud compute ssh $InstanceName --zone=$Zone --project=$ProjectId --tunnel-through-iap --command=$legacyCmd 2>&1 | Out-Null
  }
} elseif ($EnsureWorker) {
  & gcloud compute ssh $InstanceName --zone=$Zone --project=$ProjectId --tunnel-through-iap --command=$legacyCmd 2>&1 | Out-Null
}

$running = & gcloud compute ssh $InstanceName --zone=$Zone --project=$ProjectId --tunnel-through-iap --command=$checkCmd 2>&1
if ($running -match '\w') {
  Write-Rw "  Remote scrape worker: running." "Green"
  return @{ ok = $true; running = $true; ghcr = $wantGhcr }
}

Write-Rw "  Remote scrape worker: NOT running (check connect-gcp-vm.ps1 -Logs)." "Yellow"
return @{ ok = $false; running = $false }
