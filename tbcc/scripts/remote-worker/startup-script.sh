#!/usr/bin/env bash
# GCP / Linux VM first-boot: Tailscale + Docker + TBCC remote scrape worker.
# Invoked via gcloud --metadata-from-file=startup-script=...
set -euo pipefail

exec > >(tee -a /var/log/tbcc-startup.log) 2>&1
echo "==> TBCC remote worker startup $(date -u +%Y-%m-%dT%H:%M:%SZ)"

TBCC_ROOT="${TBCC_ROOT:-/opt/tbcc}"
REPO_URL="${TBCC_REPO_URL:-https://github.com/ianmxaof/tbcc3.git}"
REPO_BRANCH="${TBCC_REPO_BRANCH:-lean-stack-hardening}"
GHCR_IMAGE="${TBCC_GHCR_IMAGE:-ghcr.io/ianmxaof/tbcc-worker:latest}"
TS_HOSTNAME="${TBCC_TS_HOSTNAME:-tbcc-remote-worker}"

meta() {
  curl -sf -H "Metadata-Flavor: Google" \
    "http://metadata.google.internal/computeMetadata/v1/instance/attributes/${1}" 2>/dev/null || true
}

TAILSCALE_AUTHKEY="$(meta tbcc-tailscale-authkey)"
HOME_TS_IP="$(meta tbcc-home-tailscale-ip)"
GHCR_TOKEN="$(meta tbcc-ghcr-token)"
GHCR_USER="$(meta tbcc-ghcr-user)"
API_ID="$(meta tbcc-api-id)"
API_HASH="$(meta tbcc-api-hash)"
USE_GHCR="$(meta tbcc-use-ghcr)"
REPO_URL_META="$(meta tbcc-repo-url)"
REPO_BRANCH_META="$(meta tbcc-repo-branch)"
[[ -n "$REPO_URL_META" ]] && REPO_URL="$REPO_URL_META"
[[ -n "$REPO_BRANCH_META" ]] && REPO_BRANCH="$REPO_BRANCH_META"
img_meta="$(meta tbcc-ghcr-image)"
[[ -n "$img_meta" ]] && GHCR_IMAGE="$img_meta"
hn_meta="$(meta tbcc-ts-hostname)"
[[ -n "$hn_meta" ]] && TS_HOSTNAME="$hn_meta"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y curl git ca-certificates

if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
if [[ -n "$TAILSCALE_AUTHKEY" ]]; then
  tailscale up --authkey="$TAILSCALE_AUTHKEY" --hostname="$TS_HOSTNAME" --accept-routes || true
else
  echo "WARN: no tbcc-tailscale-authkey metadata — run: sudo tailscale up"
fi

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi

mkdir -p "$(dirname "$TBCC_ROOT")"
if [[ ! -d "$TBCC_ROOT/.git" ]]; then
  git clone --branch "$REPO_BRANCH" --depth 1 "$REPO_URL" "$TBCC_ROOT" || \
    git clone --depth 1 "$REPO_URL" "$TBCC_ROOT"
else
  git -C "$TBCC_ROOT" fetch --depth 1 origin "$REPO_BRANCH" || true
  git -C "$TBCC_ROOT" checkout "$REPO_BRANCH" 2>/dev/null || true
  git -C "$TBCC_ROOT" pull --ff-only || true
fi

INFRA="$TBCC_ROOT/infra"
mkdir -p "$INFRA/data/sessions"

ENV_FILE="$INFRA/.env.remote-worker"
if [[ ! -f "$ENV_FILE" ]]; then
  cp "$INFRA/env.remote-worker.example" "$ENV_FILE"
fi

if [[ -n "$HOME_TS_IP" ]]; then
  sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql://postgres:postgres@${HOME_TS_IP}:5432/tbcc|" "$ENV_FILE"
  sed -i "s|^REDIS_URL=.*|REDIS_URL=redis://${HOME_TS_IP}:6379/0|" "$ENV_FILE"
fi
if [[ -n "$API_ID" ]]; then
  sed -i "s|^API_ID=.*|API_ID=${API_ID}|" "$ENV_FILE"
fi
if [[ -n "$API_HASH" ]]; then
  sed -i "s|^API_HASH=.*|API_HASH=${API_HASH}|" "$ENV_FILE"
fi

cd "$INFRA"
export TBCC_WORKER_IMAGE="$GHCR_IMAGE"

if [[ "${USE_GHCR}" == "1" || "${USE_GHCR}" == "true" ]]; then
  if [[ -n "$GHCR_TOKEN" && -n "$GHCR_USER" ]]; then
    echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin || true
  fi
fi

if [[ ! -f "$INFRA/data/sessions/scraper.session" ]]; then
  echo "NOTE: scraper.session missing — sync from home PC, then:"
  echo "  TBCC_USE_GHCR=${USE_GHCR:-0} bash $TBCC_ROOT/scripts/remote-worker/install-remote-worker.sh"
  echo "Startup done (partial)."
  exit 0
fi

if [[ "${USE_GHCR}" == "1" || "${USE_GHCR}" == "true" ]]; then
  docker compose -f docker-compose.remote-worker.ghcr.yml pull || true
  docker compose -f docker-compose.remote-worker.ghcr.yml up -d
else
  docker compose -f docker-compose.remote-worker.yml up -d --build
fi

echo "==> TBCC remote worker startup complete"
