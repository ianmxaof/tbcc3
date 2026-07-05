# Launch bootstrap-gcp-instance.sh (Git Bash or WSL).
#
# Prereqs:
#   - Google Cloud SDK: https://cloud.google.com/sdk/docs/install
#   - gcloud auth login && gcloud config set project YOUR_PROJECT_ID
#   - SSH pubkey at ~/.ssh/gcp_tbcc.pub
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tbcc\scripts\gcp\bootstrap-gcp-instance.ps1
#   powershell ... -Zone us-central1-a -MachineType e2-medium -Inline

param(
  [string]$ProjectId = "",
  [string]$Zone = "us-west1-b",
  [string]$MachineType = "e2-standard-2",
  [string]$InstanceName = "tbcc-lean",
  [switch]$Inline
)

$ErrorActionPreference = "Stop"

$bashCandidates = @(
  "C:\Program Files\Git\bin\bash.exe",
  "C:\Program Files (x86)\Git\bin\bash.exe"
)
$bash = $bashCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $bash) {
  Write-Error "Git Bash not found. Install Git for Windows or use WSL with gcloud."
}

$gcpDir = $PSScriptRoot
$drive = $gcpDir.Substring(0, 1).ToLower()
$bashDir = "/$drive/$($gcpDir.Substring(3) -replace '\\', '/')"

$sshPub = Join-Path $env:USERPROFILE ".ssh\gcp_tbcc.pub"
if (-not (Test-Path $sshPub)) {
  Write-Warning "Missing $sshPub"
  Write-Host 'Generate: ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\gcp_tbcc -N ""'
  exit 1
}

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
  Write-Error "gcloud not in PATH. Install Google Cloud CLI and restart the terminal."
}

$proj = $ProjectId
if (-not $proj) {
  $proj = (gcloud config get-value project 2>$null)
}
if (-not $proj) {
  Write-Error "No GCP project. Run: gcloud config set project YOUR_PROJECT_ID"
}

$envLines = @(
  "export GCP_PROJECT_ID='$proj'"
  "export GCP_ZONE='$Zone'"
  "export GCP_MACHINE_TYPE='$MachineType'"
  "export GCP_INSTANCE_NAME='$InstanceName'"
  "export GCP_SSH_KEY_FILE='$($sshPub -replace '\\', '/')'"
)

$launcher = Join-Path $env:TEMP "tbcc-bootstrap-gcp-launch.sh"
$launcherLines = @("#!/usr/bin/env bash", "set -e", "cd '$bashDir'") + $envLines + @("bash bootstrap-gcp-instance.sh", "read -r -p 'Press Enter to close...' _")
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($launcher, $launcherLines, $utf8NoBom)

Write-Host "Launching GCP bootstrap"
Write-Host "  Project:  $proj"
Write-Host "  Zone:     $Zone"
Write-Host "  Machine:  $MachineType"
Write-Host "  Instance: $InstanceName"

if ($Inline) {
  & $bash $launcher
} else {
  Start-Process -FilePath $bash -ArgumentList $launcher
}
