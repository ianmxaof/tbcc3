# Open an SSH session to the TBCC GCP remote worker (IAP — works with or without public IP).
#
# Usage:
#   cd tbcc
#   .\scripts\remote-worker\connect-gcp-vm.ps1
#   .\scripts\remote-worker\connect-gcp-vm.ps1 -Logs
#   .\scripts\remote-worker\connect-gcp-vm.ps1 -StartupLog
#
param(
  [string]$ProjectId = "tbcc-cloud-instance",
  [string]$Zone = "us-west1-a",
  [string]$InstanceName = "tbcc-remote-worker",
  [switch]$Logs,
  [switch]$StartupLog
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
  throw "gcloud not found. Install Google Cloud SDK first."
}

if ($StartupLog) {
  & gcloud compute instances get-serial-port-output $InstanceName --zone=$Zone --project=$ProjectId
  exit $LASTEXITCODE
}

$base = @(
  "compute", "ssh", $InstanceName,
  "--zone=$Zone",
  "--project=$ProjectId",
  "--tunnel-through-iap"
)

if ($Logs) {
  # Avoid `-f` in --command (gcloud treats it as its own flag). Use --tail, not follow.
  $compose = "/opt/tbcc/infra/docker-compose.remote-worker.yml"
  $cmd = "docker compose -f $compose logs --tail=80 worker_scrape 2>&1"
  & gcloud @base --command=$cmd
} else {
  & gcloud @base
}
