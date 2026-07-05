#!/usr/bin/env bash
# Create a TBCC lean-stack VM on Google Cloud (Ubuntu 24.04, Docker via startup script).
#
# Prereqs (on your PC):
#   gcloud auth login
#   gcloud config set project YOUR_PROJECT_ID
#   gcloud services enable compute.googleapis.com
#
# Windows:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tbcc\scripts\gcp\bootstrap-gcp-instance.ps1
#
# Optional env:
#   GCP_PROJECT_ID          (default: gcloud config project)
#   GCP_ZONE=us-west1-b
#   GCP_MACHINE_TYPE=e2-standard-2   # 2 vCPU / 8 GB — recommended for lean stack
#   GCP_INSTANCE_NAME=tbcc-lean
#   GCP_BOOT_DISK_GB=50
#   GCP_SSH_KEY_FILE=$HOME/.ssh/gcp_tbcc.pub
set -euo pipefail

GCP_PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
GCP_ZONE="${GCP_ZONE:-us-west1-b}"
GCP_MACHINE_TYPE="${GCP_MACHINE_TYPE:-e2-standard-2}"
GCP_INSTANCE_NAME="${GCP_INSTANCE_NAME:-tbcc-lean}"
GCP_BOOT_DISK_GB="${GCP_BOOT_DISK_GB:-50}"
GCP_SSH_KEY_FILE="${GCP_SSH_KEY_FILE:-$HOME/.ssh/gcp_tbcc.pub}"
GCP_FIREWALL_RULE="${GCP_FIREWALL_RULE:-tbcc-allow-iap-ssh}"

if [[ -z "${GCP_PROJECT_ID}" || "${GCP_PROJECT_ID}" == "(unset)" ]]; then
  echo "Set GCP project: gcloud config set project YOUR_PROJECT_ID"
  exit 1
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "Install Google Cloud CLI: https://cloud.google.com/sdk/docs/install"
  exit 1
fi

if [[ ! -f "$GCP_SSH_KEY_FILE" ]]; then
  echo "Missing SSH public key: $GCP_SSH_KEY_FILE"
  echo 'Generate: ssh-keygen -t ed25519 -f ~/.ssh/gcp_tbcc -N ""'
  exit 1
fi

echo "==> Project:  $GCP_PROJECT_ID"
echo "==> Zone:     $GCP_ZONE"
echo "==> Machine:  $GCP_MACHINE_TYPE"
echo "==> Instance: $GCP_INSTANCE_NAME"

# IAP-only SSH — no public Postgres/Redis/API ports
if ! gcloud compute firewall-rules describe "$GCP_FIREWALL_RULE" --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
  echo "==> Creating firewall rule $GCP_FIREWALL_RULE (IAP TCP forwarding for SSH)"
  gcloud compute firewall-rules create "$GCP_FIREWALL_RULE" \
    --project="$GCP_PROJECT_ID" \
    --direction=INGRESS \
    --priority=1000 \
    --network=default \
    --action=ALLOW \
    --rules=tcp:22 \
    --source-ranges=35.235.240.0/20 \
    --target-tags=tbcc-ssh \
    --description="TBCC SSH via IAP tunnel only"
else
  echo "==> Firewall rule $GCP_FIREWALL_RULE already exists"
fi

STARTUP_SCRIPT="$(mktemp)"
cat >"$STARTUP_SCRIPT" <<'EOF'
#!/bin/bash
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl ca-certificates
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
usermod -aG docker ubuntu 2>/dev/null || true
mkdir -p /opt/tbcc
chown ubuntu:ubuntu /opt/tbcc
EOF

if gcloud compute instances describe "$GCP_INSTANCE_NAME" --zone="$GCP_ZONE" --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
  echo "Instance $GCP_INSTANCE_NAME already exists in $GCP_ZONE"
else
  echo "==> Creating VM..."
  gcloud compute instances create "$GCP_INSTANCE_NAME" \
    --project="$GCP_PROJECT_ID" \
    --zone="$GCP_ZONE" \
    --machine-type="$GCP_MACHINE_TYPE" \
    --image-family=ubuntu-2404-lts-amd64 \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size="${GCP_BOOT_DISK_GB}GB" \
    --boot-disk-type=pd-balanced \
    --tags=tbcc-ssh \
    --metadata="ssh-keys=ubuntu:$(cat "$GCP_SSH_KEY_FILE")" \
    --metadata-from-file=startup-script="$STARTUP_SCRIPT" \
    --scopes=cloud-platform
fi

rm -f "$STARTUP_SCRIPT"

EXTERNAL_IP="$(gcloud compute instances describe "$GCP_INSTANCE_NAME" \
  --zone="$GCP_ZONE" --project="$GCP_PROJECT_ID" \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)' 2>/dev/null || true)"

echo ""
echo "Done."
echo "  Instance: $GCP_INSTANCE_NAME"
echo "  Zone:     $GCP_ZONE"
echo "  External: ${EXTERNAL_IP:-none}"
echo ""
echo "SSH (IAP tunnel — recommended):"
echo "  gcloud compute ssh $GCP_INSTANCE_NAME --zone=$GCP_ZONE --project=$GCP_PROJECT_ID"
echo ""
echo "Next:"
echo "  1. Clone TBCC on the VM (or sync from home — see docs/GCP_VPS.md)"
echo "  2. bash /opt/tbcc/tbcc/scripts/gcp/install-gcp-lean-stack.sh"
echo "  3. From home: .\\scripts\\gcp\\sync-stack-to-gcp.ps1 -RemoteHost <ip-or-iap> -RemoteUser ubuntu"
