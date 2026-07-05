# Launch bootstrap-oci-instance.sh in Git Bash (OCI VM create / capacity hunt).
#
# Prereqs:
#   - OCI CLI configured (~/.oci/config) - run write-oci-config.ps1 first
#   - SSH pubkey at ~/.ssh/oci_tbcc.pub
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tbcc\scripts\remote-worker\bootstrap-oci-instance.ps1
#
# Optional:
#   -RotateRegions          Hunt all subscribed regions (default: home region only)
#   -Region us-phoenix-1     Override OCI_CLI_REGION
#   -Inline                 Run in this PowerShell window instead of opening Git Bash

param(
  [switch]$RotateRegions,
  [string]$Region = "us-sanjose-1",
  [switch]$Inline
)

$ErrorActionPreference = "Stop"

$bashCandidates = @(
  "C:\Program Files\Git\bin\bash.exe",
  "C:\Program Files (x86)\Git\bin\bash.exe"
)
$bash = $bashCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $bash) {
  Write-Error "Git Bash not found. Install Git for Windows: https://git-scm.com/download/win"
}

$workerDir = $PSScriptRoot
$drive = $workerDir.Substring(0, 1).ToLower()
$bashDir = "/$drive/$($workerDir.Substring(3) -replace '\\', '/')"

$ociConfig = Join-Path $env:USERPROFILE ".oci\config"
if (-not (Test-Path $ociConfig)) {
  Write-Error "Missing $ociConfig. Run write-oci-config.ps1 first."
}

$sshPub = Join-Path $env:USERPROFILE ".ssh\oci_tbcc.pub"
if (-not (Test-Path $sshPub)) {
  Write-Warning "Missing $sshPub"
  Write-Host 'Generate: ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\oci_tbcc -N ""'
  exit 1
}

$rotate = if ($RotateRegions) { "true" } else { "false" }

# Write a small bash launcher so Windows PowerShell 5.1 does not parse && / nested quotes.
$launcher = Join-Path $env:TEMP "tbcc-bootstrap-oci-launch.sh"
$launcherLines = @(
  "#!/usr/bin/env bash"
  "set +e"
  "cd '$bashDir'"
  "export OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True"
  "export OCI_CLI_REGION='$Region'"
  "export ROTATE_REGIONS='$rotate'"
  "export MAX_ROUNDS=0"
  "while true; do"
  "  bash bootstrap-oci-instance.sh"
  "  ec=`$?"
  "  if [ `$ec -eq 0 ]; then break; fi"
  "  if [ `$ec -eq 1 ]; then exit 1; fi"
  "  echo"
  "  echo '==> Launcher backup retry in 30s...'"
  "  sleep 30"
  "done"
  "echo"
  "read -r -p 'Press Enter to close...' _"
)
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($launcher, $launcherLines, $utf8NoBom)

Write-Host "Launching OCI bootstrap in Git Bash"
Write-Host "  Directory: $bashDir"
Write-Host "  Region:    $Region"
Write-Host "  Rotate:    $rotate (subscribed regions only when true)"
Write-Host "  Leave the Git Bash window open - it retries every 30s until capacity is found."

if ($Inline) {
  & $bash --login $launcher
  exit $LASTEXITCODE
}

Start-Process -FilePath $bash -ArgumentList @("--login", $launcher)
Write-Host "Git Bash window opened."
