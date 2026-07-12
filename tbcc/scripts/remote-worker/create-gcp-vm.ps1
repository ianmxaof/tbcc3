# Create a GCP Compute Engine VM for TBCC remote Celery scrape worker.
# Architecture: home Windows stack + this VM (scrape queue only). See tbcc/docs/REMOTE_WORKER.md
#
# Prerequisites on this PC:
#   - gcloud CLI: https://cloud.google.com/sdk/docs/install
#   - gcloud auth login
#   - Optional: TBCC_TAILSCALE_AUTHKEY in tbcc/.env (ephemeral key from Tailscale admin)
#
# Usage:
#   cd tbcc
#   .\scripts\remote-worker\create-gcp-vm.ps1 -ProjectId "tbcc-cloud-instance"
#   .\scripts\remote-worker\create-gcp-vm.ps1 -ProjectId "..." -UseGhcr -WhatIf
#
param(
  [Parameter(Mandatory = $true)]
  [string]$ProjectId,

  [string]$Zone = "us-west1-a",
  [string]$InstanceName = "tbcc-remote-worker",
  [string]$MachineType = "e2-micro",
  [int]$BootDiskGb = 30,

  # No public IP — access via: gcloud compute ssh --tunnel-through-iap
  [switch]$NoExternalIp = $true,

  # Create IAP SSH firewall rule (required when -NoExternalIp)
  [switch]$EnsureIapFirewall = $true,

  # Attach startup-script.sh (Tailscale + Docker + clone)
  [switch]$WithStartupScript = $true,

  # Prefer GHCR image pull on the VM (set metadata tbcc-use-ghcr=1)
  [switch]$UseGhcr,

  [string]$GhcrImage = "ghcr.io/ianmxaof/tbcc-worker:latest",
  [string]$RepoUrl = "https://github.com/ianmxaof/tbcc3.git",
  [string]$RepoBranch = "lean-stack-hardening",

  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

function Invoke-GCloud {
  param([string[]]$CliArgs)
  $safe = ($CliArgs -join " ") -replace 'tbcc-api-hash=[^, ]+', 'tbcc-api-hash=***' `
    -replace 'tbcc-api-id=[^, ]+', 'tbcc-api-id=***' `
    -replace 'tbcc-tailscale-authkey=[^, ]+', 'tbcc-tailscale-authkey=***' `
    -replace 'tbcc-ghcr-token=[^, ]+', 'tbcc-ghcr-token=***'
  Write-Host ("gcloud " + $safe) -ForegroundColor DarkGray
  if ($WhatIf) { return }
  & gcloud @CliArgs
  if ($LASTEXITCODE -ne 0) {
    throw "gcloud failed (exit $LASTEXITCODE)"
  }
}

# PSScriptRoot = tbcc/scripts/remote-worker → tbcc root is two parents up
$tbccRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$startupScript = Join-Path $PSScriptRoot "startup-script.sh"

function Get-TbccEnvValue([string]$Name) {
  $envFile = Join-Path $tbccRoot ".env"
  if (-not (Test-Path -LiteralPath $envFile)) { return "" }
  foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
    if ($line -match "^\s*$([regex]::Escape($Name))\s*=\s*(.*)$") {
      return $Matches[1].Trim().Trim('"').Trim("'")
    }
  }
  return ""
}

Write-Host "TBCC GCP remote worker - create VM" -ForegroundColor Cyan
Write-Host "  Project:  $ProjectId"
Write-Host "  Zone:     $Zone"
Write-Host "  Instance: $InstanceName"
Write-Host ("  Type:     {0} ({1} GB Ubuntu 24.04)" -f $MachineType, $BootDiskGb)
Write-Host "  Startup:  $WithStartupScript"
Write-Host "  GHCR:     $UseGhcr"
Write-Host ""

if (-not $WhatIf) {
  $gcloud = Get-Command gcloud -ErrorAction SilentlyContinue
  if (-not $gcloud) {
    throw "gcloud not found. Install Google Cloud SDK and re-run."
  }
}

Invoke-GCloud @("config", "set", "project", $ProjectId)

Write-Host "Enabling Compute + IAP APIs (safe if already on)..." -ForegroundColor Yellow
Invoke-GCloud @("services", "enable", "compute.googleapis.com", "iap.googleapis.com", "--project=$ProjectId")

if ($EnsureIapFirewall -and $NoExternalIp) {
  $fwName = "tbcc-allow-iap-ssh"
  Write-Host "Ensuring firewall rule $fwName (TCP 22 from IAP range)..." -ForegroundColor Yellow
  if (-not $WhatIf) {
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $null = & gcloud compute firewall-rules describe $fwName --project=$ProjectId 2>$null
    $fwMissing = $LASTEXITCODE -ne 0
    $ErrorActionPreference = $prevEap
    if ($fwMissing) {
      Invoke-GCloud @(
        "compute", "firewall-rules", "create", $fwName,
        "--project=$ProjectId",
        "--direction=INGRESS",
        "--action=ALLOW",
        "--rules=tcp:22",
        "--source-ranges=35.235.240.0/20",
        "--target-tags=tbcc-remote-worker",
        "--description=SSH via Identity-Aware Proxy for TBCC remote worker (no public IP)"
      )
    } else {
      Write-Host "  Firewall rule already exists - skip." -ForegroundColor DarkGray
    }
  }
}

# Build metadata
$metaPairs = @(
  "enable-oslogin=TRUE",
  "tbcc-repo-url=$RepoUrl",
  "tbcc-repo-branch=$RepoBranch",
  "tbcc-ghcr-image=$GhcrImage",
  "tbcc-ts-hostname=$InstanceName"
)
if ($UseGhcr) {
  $metaPairs += "tbcc-use-ghcr=1"
}

$tsKey = Get-TbccEnvValue "TBCC_TAILSCALE_AUTHKEY"
$homeTs = Get-TbccEnvValue "TBCC_HOME_TAILSCALE_IP"
if (-not $homeTs) {
  try {
    $homeTs = (& tailscale ip -4 2>$null | Select-Object -First 1)
    if ($homeTs) { $homeTs = $homeTs.Trim() }
  } catch { }
}
$ghcrToken = Get-TbccEnvValue "TBCC_GHCR_TOKEN"
$ghcrUser = Get-TbccEnvValue "TBCC_GHCR_USER"
if (-not $ghcrUser) { $ghcrUser = Get-TbccEnvValue "TBCC_GITHUB_USER" }
$apiId = Get-TbccEnvValue "API_ID"
if (-not $apiId) { $apiId = Get-TbccEnvValue "TELEGRAM_API_ID" }
$apiHash = Get-TbccEnvValue "API_HASH"
if (-not $apiHash) { $apiHash = Get-TbccEnvValue "TELEGRAM_API_HASH" }

if ($homeTs) { $metaPairs += "tbcc-home-tailscale-ip=$homeTs" }
if ($tsKey) { $metaPairs += "tbcc-tailscale-authkey=$tsKey" }
if ($ghcrToken) { $metaPairs += "tbcc-ghcr-token=$ghcrToken" }
if ($ghcrUser) { $metaPairs += "tbcc-ghcr-user=$ghcrUser" }
if ($apiId) { $metaPairs += "tbcc-api-id=$apiId" }
if ($apiHash) { $metaPairs += "tbcc-api-hash=$apiHash" }

$metaJoined = $metaPairs -join ","

$createArgs = @(
  "compute", "instances", "create", $InstanceName,
  "--project=$ProjectId",
  "--zone=$Zone",
  "--machine-type=$MachineType",
  "--network-interface=network=default,network-tier=STANDARD",
  "--tags=tbcc-remote-worker",
  "--metadata=$metaJoined",
  "--maintenance-policy=MIGRATE",
  "--provisioning-model=STANDARD",
  "--scopes=default",
  "--image-family=ubuntu-2404-lts-amd64",
  "--image-project=ubuntu-os-cloud",
  "--boot-disk-size=${BootDiskGb}GB",
  "--boot-disk-type=pd-standard",
  "--boot-disk-auto-delete"
)

if ($WithStartupScript) {
  if (-not (Test-Path -LiteralPath $startupScript)) {
    throw "Missing startup script: $startupScript"
  }
  $createArgs += "--metadata-from-file=startup-script=$startupScript"
}

if ($NoExternalIp) {
  $createArgs += "--no-address"
}

if (-not $tsKey -and $WithStartupScript) {
  Write-Host 'WARN: TBCC_TAILSCALE_AUTHKEY not in tbcc/.env - VM will need manual: sudo tailscale up' -ForegroundColor Yellow
  Write-Host '  Create ephemeral key: https://login.tailscale.com/admin/settings/keys' -ForegroundColor DarkYellow
  Write-Host '  Then: .\scripts\tbcc-secret.ps1 -Key TBCC_TAILSCALE_AUTHKEY -FromClipboard' -ForegroundColor DarkYellow
}

Write-Host "Creating instance..." -ForegroundColor Yellow
Invoke-GCloud $createArgs

if ($WhatIf) {
  Write-Host "WhatIf - no resources created." -ForegroundColor Yellow
  exit 0
}

Write-Host ""
Write-Host "VM created." -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Wait ~2-5 min for startup-script (Tailscale + Docker + clone)."
Write-Host "     Serial log: gcloud compute instances get-serial-port-output $InstanceName --zone=$Zone --project=$ProjectId"
Write-Host ""
Write-Host "  2. SSH (IAP):"
Write-Host "     .\scripts\remote-worker\connect-gcp-vm.ps1 -ProjectId $ProjectId -Zone $Zone"
Write-Host ""
Write-Host '  3. Note VM Tailscale IP, set on home:'
Write-Host '     TBCC_REMOTE_STACK_HOST=100.x.y.z'
Write-Host '     TBCC_CELERY_HOME_QUEUES=celery,subscription,telegram'
Write-Host '     Or: .\scripts\remote-worker\enable-home-offload.ps1 -RemoteHost 100.x.y.z'
Write-Host ""
Write-Host '  4. Sync scraper.session:'
Write-Host '     .\scripts\remote-worker\sync-scraper-session.ps1 -RemoteHost 100.x.y.z -RemoteUser ubuntu'
Write-Host ""
Write-Host '  5. Start worker on VM (if session was missing at boot):'
Write-Host '     bash /opt/tbcc/scripts/remote-worker/install-remote-worker.sh'
Write-Host '     # or with GHCR: TBCC_USE_GHCR=1 bash .../install-remote-worker.sh'
Write-Host ""
Write-Host "Full guide: tbcc/docs/REMOTE_WORKER.md"
