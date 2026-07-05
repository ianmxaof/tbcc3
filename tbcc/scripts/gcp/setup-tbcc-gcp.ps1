# One-shot TBCC lean stack on Google Cloud — run from repo root or tbcc/.
#
# Does everything:
#   1. gcloud prereqs + SSH key
#   2. Create VM (if missing) + IAP firewall
#   3. Upload tbcc code + .env + Telethon sessions
#   4. Docker install + migrations + compose up
#   5. Health check
#
# Prereqs (once):
#   gcloud auth login
#   gcloud config set project YOUR_PROJECT_ID
#
# Usage:
#   cd c:\path\to\telegram_bot2
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tbcc\scripts\gcp\setup-tbcc-gcp.ps1
#
# Options:
#   -SkipVmCreate     VM already exists — only sync + install
#   -SkipInstall      Only create VM + upload files
#   -Zone us-central1-a -MachineType e2-medium

param(
  [string]$ProjectId = "",
  [string]$Zone = "us-west1-b",
  [string]$MachineType = "e2-standard-2",
  [string]$InstanceName = "tbcc-lean",
  [int]$BootDiskGb = 50,
  [string]$RemoteRepoRoot = "/opt/telegram_bot2",
  [string]$RepoUrl = "",
  [switch]$SkipVmCreate,
  [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

# --- paths ---
$gcpDir = $PSScriptRoot
if (Test-Path (Join-Path $gcpDir "..\..\backend")) {
  $tbccRoot = (Resolve-Path (Join-Path $gcpDir "..\..")).Path
} else {
  $repoRoot = (Resolve-Path (Join-Path $gcpDir "..\..")).Path
  $tbccRoot = Join-Path $repoRoot "tbcc"
}
$backend = Join-Path $tbccRoot "backend"
$infra = Join-Path $tbccRoot "infra"
$localEnv = Join-Path $tbccRoot ".env"
$remoteTbcc = "$RemoteRepoRoot/tbcc"
$remoteInfra = "$remoteTbcc/infra"

function Write-Step([string]$Msg) {
  Write-Host ""
  Write-Host "==> $Msg" -ForegroundColor Cyan
}

function Get-GcpProject {
  if ($ProjectId) { return $ProjectId }
  $p = (gcloud config get-value project 2>$null)
  if (-not $p) { throw "No GCP project. Run: gcloud config set project YOUR_PROJECT_ID" }
  return $p.Trim()
}

function Invoke-GcpSsh([string]$Cmd) {
  gcloud compute ssh $InstanceName --zone=$Zone --project=$script:Project --command=$Cmd 2>&1
  if ($LASTEXITCODE -ne 0) { throw "Remote command failed: $Cmd" }
}

function Copy-GcpScp([string]$Local, [string]$RemoteDest) {
  gcloud compute scp --recurse $Local "ubuntu@${InstanceName}:${RemoteDest}" --zone=$Zone --project=$script:Project
  if ($LASTEXITCODE -ne 0) { throw "scp failed: $Local -> $RemoteDest" }
}

function Copy-GcpScpFile([string]$Local, [string]$RemoteDest) {
  gcloud compute scp $Local "ubuntu@${InstanceName}:${RemoteDest}" --zone=$Zone --project=$script:Project
  if ($LASTEXITCODE -ne 0) { throw "scp failed: $Local -> $RemoteDest" }
}

function Ensure-SshKey {
  $priv = Join-Path $env:USERPROFILE ".ssh\gcp_tbcc"
  $pub = "$priv.pub"
  if (-not (Test-Path $pub)) {
    Write-Step "Generating SSH key $priv"
    ssh-keygen -t ed25519 -f $priv -N '""' | Out-Null
  }
  return $pub
}

function Build-GcpEnvFile {
  $template = Join-Path $infra "env.gcp-lean.example"
  if (-not (Test-Path $template)) { throw "Missing $template" }
  $local = @{}
  if (Test-Path $localEnv) {
    Get-Content $localEnv | ForEach-Object {
      $t = $_.Trim()
      if (-not $t -or $t.StartsWith("#") -or $t -notmatch "=") { return }
      $k, $v = $t -split "=", 2
      $local[$k.Trim()] = $v.Trim().Trim('"').Trim("'")
    }
  } else {
    Write-Warning "No $localEnv — fill secrets on VM after upload"
  }
  $pgPass = if ($local["POSTGRES_PASSWORD"]) { $local["POSTGRES_PASSWORD"] } else {
    -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
  }
  if (-not $local["POSTGRES_PASSWORD"]) {
    Write-Host "  Generated POSTGRES_PASSWORD (saved in uploaded .env.gcp-lean)" -ForegroundColor Yellow
  }
  $out = New-Object System.Collections.ArrayList
  foreach ($line in (Get-Content $template)) {
    if ($line -match '^([A-Z0-9_]+)=(.*)$' -and $local.ContainsKey($Matches[1])) {
      $key = $Matches[1]
      if ($key -eq "DATABASE_URL" -and $local[$key] -match "sqlite") { [void]$out.Add($line); continue }
      if ($key -in @("TELEGRAM_SESSION_PATH", "TBCC_POSTER_TELEGRAM_SESSION", "TBCC_IMPORT_TELEGRAM_SESSION", "TBCC_ALBUM_COMPOSER_TELEGRAM_SESSION", "TBCC_SCRAPER_TELEGRAM_SESSION")) { continue }
      [void]$out.Add("$key=$($local[$key])")
    } else {
      [void]$out.Add($line)
    }
  }
  $filtered = $out | Where-Object {
    $_ -notmatch '^DATABASE_URL=' -and $_ -notmatch '^REDIS_URL=' -and $_ -notmatch '^POSTGRES_PASSWORD=' -and $_ -notmatch '^TBCC_API_URL='
  }
  $final = @(
    "DATABASE_URL=postgresql://postgres:${pgPass}@postgres:5432/tbcc"
    "REDIS_URL=redis://redis:6379/0"
    "POSTGRES_PASSWORD=$pgPass"
    "TBCC_API_URL=http://api:8000"
    "TBCC_STACK_PROFILE=lean"
    "TBCC_BOT_RUNTIME_ADAPTER=command"
  ) + $filtered
  $path = Join-Path $env:TEMP "tbcc-gcp-lean-$([Guid]::NewGuid().ToString('n').Substring(0,8)).env"
  $final | Set-Content -Encoding utf8 $path
  return $path
}

function New-StartupScriptFile {
  $f = Join-Path $env:TEMP "tbcc-gcp-startup.sh"
  @'
#!/bin/bash
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl ca-certificates
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
usermod -aG docker ubuntu 2>/dev/null || true
mkdir -p /opt/telegram_bot2
chown -R ubuntu:ubuntu /opt/telegram_bot2
'@ | Set-Content -Encoding utf8 $f
  return $f
}

function Wait-SshReady {
  param([int]$MaxSeconds = 300)
  Write-Step "Waiting for SSH (up to ${MaxSeconds}s)..."
  $deadline = (Get-Date).AddSeconds($MaxSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $r = gcloud compute ssh $InstanceName --zone=$Zone --project=$script:Project --command="echo ready" 2>&1
      if ($LASTEXITCODE -eq 0 -and ($r -match "ready")) {
        Write-Host "  SSH OK"
        return
      }
    } catch { }
    Write-Host "  ... still booting ($(Get-Date -Format 'HH:mm:ss'))"
    Start-Sleep -Seconds 15
  }
  throw "SSH not ready after ${MaxSeconds}s. Try: gcloud compute ssh $InstanceName --zone=$Zone"
}

# ========== MAIN ==========

Write-Host @"

  TBCC GCP one-shot setup
  -----------------------

"@ -ForegroundColor Green

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
  throw "Install Google Cloud CLI: https://cloud.google.com/sdk/docs/install"
}

$script:Project = Get-GcpProject
Write-Host "  Project:  $script:Project"
Write-Host "  Zone:     $Zone"
Write-Host "  Instance: $InstanceName"
Write-Host "  TBCC:     $tbccRoot"

$sshPub = Ensure-SshKey
$pubContent = (Get-Content $sshPub -Raw).Trim()

if (-not $SkipVmCreate) {
  Write-Step "Enabling Compute API"
  gcloud services enable compute.googleapis.com --project=$script:Project | Out-Null

  $fw = "tbcc-allow-iap-ssh"
  $fwExists = gcloud compute firewall-rules describe $fw --project=$script:Project 2>$null
  if (-not $fwExists) {
    Write-Step "Creating IAP SSH firewall rule"
    gcloud compute firewall-rules create $fw `
      --project=$script:Project `
      --direction=INGRESS --priority=1000 --network=default `
      --action=ALLOW --rules=tcp:22 `
      --source-ranges=35.235.240.0/20 `
      --target-tags=tbcc-ssh `
      --description="TBCC SSH via IAP" | Out-Null
  }

  $exists = gcloud compute instances describe $InstanceName --zone=$Zone --project=$script:Project 2>$null
  if (-not $exists) {
    Write-Step "Creating VM $InstanceName ($MachineType, ${BootDiskGb}GB)"
    $startup = New-StartupScriptFile
    gcloud compute instances create $InstanceName `
      --project=$script:Project `
      --zone=$Zone `
      --machine-type=$MachineType `
      --image-family=ubuntu-2404-lts-amd64 `
      --image-project=ubuntu-os-cloud `
      --boot-disk-size="${BootDiskGb}GB" `
      --boot-disk-type=pd-balanced `
      --tags=tbcc-ssh `
      --metadata="ssh-keys=ubuntu:$pubContent" `
      --metadata-from-file=startup-script=$startup `
      --scopes=cloud-platform
    Remove-Item $startup -Force -ErrorAction SilentlyContinue
  } else {
    Write-Host "  VM already exists — skipping create"
  }

  Wait-SshReady
} else {
  Write-Step "SkipVmCreate — checking SSH"
  Wait-SshReady -MaxSeconds 60
}

Write-Step "Preparing remote directories"
Invoke-GcpSsh "sudo mkdir -p $RemoteRepoRoot && sudo chown -R ubuntu:ubuntu $RemoteRepoRoot"
Invoke-GcpSsh "mkdir -p $remoteInfra/data/sessions $remoteInfra/data/media"

Write-Step "Uploading TBCC code (tarball — fast, includes your local tree)"
$tarPath = Join-Path $env:TEMP "tbcc-upload.tar.gz"
if (Test-Path $tarPath) { Remove-Item $tarPath -Force }
# tar from parent so extract lands as tbcc/
$tarParent = Split-Path $tbccRoot -Parent
$tarName = Split-Path $tbccRoot -Leaf
Push-Location $tarParent
try {
  & tar -czf $tarPath $tarName
  if ($LASTEXITCODE -ne 0) { throw "tar failed" }
} finally {
  Pop-Location
}
Copy-GcpScpFile $tarPath "/tmp/tbcc-upload.tar.gz"
Invoke-GcpSsh "mkdir -p $RemoteRepoRoot && tar -xzf /tmp/tbcc-upload.tar.gz -C $RemoteRepoRoot && rm -f /tmp/tbcc-upload.tar.gz && chown -R ubuntu:ubuntu $RemoteRepoRoot"
Remove-Item $tarPath -Force -ErrorAction SilentlyContinue

Write-Step "Uploading .env.gcp-lean"
$gcpEnv = Build-GcpEnvFile
Copy-GcpScpFile $gcpEnv "$remoteInfra/.env.gcp-lean"
Remove-Item $gcpEnv -Force -ErrorAction SilentlyContinue

Write-Step "Uploading Telethon sessions"
$sessionNames = @(
  "admin.session", "admin.session-wal", "admin.session-shm",
  "admin_poster.session", "admin_poster.session-wal", "admin_poster.session-shm",
  "admin_import.session", "admin_import.session-wal", "admin_import.session-shm",
  "admin_album.session", "admin_album.session-wal", "admin_album.session-shm",
  "scraper.session", "scraper.session-wal", "scraper.session-shm"
)
$missingRequired = $false
foreach ($name in $sessionNames) {
  $lp = Join-Path $backend $name
  if (-not (Test-Path -LiteralPath $lp)) {
    if ($name -match '\.(wal|shm)$') { continue }
    if ($name -eq "admin.session" -or $name -eq "admin_poster.session") { $missingRequired = $true }
    Write-Warning "  Missing $name"
    continue
  }
  Write-Host "  $name"
  Copy-GcpScpFile $lp "$remoteInfra/data/sessions/"
}
if ($missingRequired) {
  Write-Warning "admin.session and admin_poster.session are required. Copy after login on home PC."
}

if (-not $SkipInstall) {
  Write-Step "Installing Docker stack on VM (build + migrate + up — 5-15 min first run)"
  $install = "export TBCC_ROOT=$remoteTbcc REPO_DIR=$RemoteRepoRoot; bash $remoteTbcc/scripts/gcp/install-gcp-lean-stack.sh"
  Invoke-GcpSsh $install

  Write-Step "Health check"
  try {
    Invoke-GcpSsh "bash $remoteTbcc/scripts/gcp/health-gcp-stack.sh"
  } catch {
    Write-Warning "Health script reported issues — check logs on VM"
  }
}

$ip = (gcloud compute instances describe $InstanceName --zone=$Zone --project=$script:Project --format="get(networkInterfaces[0].accessConfigs[0].natIP)" 2>$null)

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " TBCC GCP setup complete" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  SSH:    gcloud compute ssh $InstanceName --zone=$Zone --project=$script:Project"
Write-Host "  Health: curl -s http://127.0.0.1:8000/health  (on VM)"
Write-Host "  Logs:   cd $remoteInfra && docker compose -f docker-compose.gcp-lean.yml logs -f api celery"
Write-Host ""
Write-Host "  STOP home TBCC tray/bots before using GCP (Telegram 409 if both run)."
Write-Host "  Expose API: Cloudflare Tunnel -> http://127.0.0.1:8000 on the VM."
Write-Host "  Docs: tbcc/docs/GCP_VPS.md"
Write-Host ""
