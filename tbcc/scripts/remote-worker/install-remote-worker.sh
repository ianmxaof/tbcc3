#!/usr/bin/env bash
# Bootstrap Linux VM for TBCC remote scrape worker.
# Prefer GHCR pull (TBCC_USE_GHCR=1) to avoid docker build CPU on small VMs.
set -euo pipefail

TBCC_ROOT="${TBCC_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
INFRA="$TBCC_ROOT/infra"
USE_GHCR="${TBCC_USE_GHCR:-0}"
GHCR_IMAGE="${TBCC_WORKER_IMAGE:-ghcr.io/ianmxaof/tbcc-worker:latest}"

echo "==> TBCC remote worker bootstrap"
echo "    TBCC root: $TBCC_ROOT"
echo "    Mode: $([[ "$USE_GHCR" == "1" || "$USE_GHCR" == "true" ]] && echo "GHCR pull ($GHCR_IMAGE)" || echo "local docker build")"

if ! command -v docker >/dev/null 2>&1; then
  echo "Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER" 2>/dev/null || true
  echo "Log out and back in so docker group applies, then re-run this script."
  exit 0
fi

mkdir -p "$INFRA/data/sessions"

if [[ ! -f "$INFRA/.env.remote-worker" ]]; then
  cp "$INFRA/env.remote-worker.example" "$INFRA/.env.remote-worker"
  echo "Created $INFRA/.env.remote-worker — edit DATABASE_URL, REDIS_URL, API_ID, API_HASH"
fi

if [[ ! -f "$INFRA/data/sessions/scraper.session" ]]; then
  echo ""
  echo "MISSING: $INFRA/data/sessions/scraper.session"
  echo "From your Windows PC run:"
  echo "  .\\scripts\\remote-worker\\sync-scraper-session.ps1 -RemoteHost <tailscale-ip> -RemoteUser ubuntu"
  echo ""
  exit 1
fi

cd "$INFRA"
if [[ "$USE_GHCR" == "1" || "$USE_GHCR" == "true" ]]; then
  export TBCC_WORKER_IMAGE="$GHCR_IMAGE"
  if [[ -n "${TBCC_GHCR_TOKEN:-}" && -n "${TBCC_GHCR_USER:-}" ]]; then
    echo "$TBCC_GHCR_TOKEN" | docker login ghcr.io -u "$TBCC_GHCR_USER" --password-stdin
  fi
  docker compose -f docker-compose.remote-worker.ghcr.yml pull
  docker compose -f docker-compose.remote-worker.ghcr.yml up -d
  COMPOSE="docker-compose.remote-worker.ghcr.yml"
else
  docker compose -f docker-compose.remote-worker.yml up -d --build
  COMPOSE="docker-compose.remote-worker.yml"
fi

echo ""
echo "Remote scrape worker started. Verify:"
echo "  docker compose -f $COMPOSE logs -f worker_scrape"
echo "  bash $TBCC_ROOT/scripts/remote-worker/health-remote-worker.sh"
echo "Update image later: bash $TBCC_ROOT/scripts/remote-worker/pull-remote-worker.sh"
