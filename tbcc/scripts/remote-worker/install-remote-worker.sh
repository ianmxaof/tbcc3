#!/usr/bin/env bash
# Bootstrap Oracle / Hetzner / any Linux VM for TBCC remote scrape worker.
set -euo pipefail

TBCC_ROOT="${TBCC_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
INFRA="$TBCC_ROOT/infra"

echo "==> TBCC remote worker bootstrap"
echo "    TBCC root: $TBCC_ROOT"

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
docker compose -f docker-compose.remote-worker.yml up -d --build

echo ""
echo "Remote scrape worker started. Verify:"
echo "  docker compose -f docker-compose.remote-worker.yml logs -f worker_scrape"
echo "  bash $TBCC_ROOT/scripts/remote-worker/health-remote-worker.sh"
