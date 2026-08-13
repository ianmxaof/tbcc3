#!/usr/bin/env bash
# Bring up revenue island API plane only (postgres redis api worker worker_telegram worker_post beat).
# NEVER starts payment_bot / loot_bot — use up-island-bots.sh after home bots are down.
#
# Expects layout from sync-island-files.ps1:
#   /opt/tbcc/infra/docker-compose.revenue-island.yml
#   /opt/tbcc/infra/.env.revenue-island
#
# Usage on VPS:
#   bash /opt/tbcc/scripts/revenue-island/bootstrap-island.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INFRA="${ROOT}/infra"
COMPOSE="${INFRA}/docker-compose.revenue-island.yml"
ENVF="${INFRA}/.env.revenue-island"

if [[ ! -f "$COMPOSE" ]]; then
  echo "Missing $COMPOSE — run sync-island-files.ps1 from home first." >&2
  exit 1
fi

if [[ ! -f "$ENVF" ]]; then
  if [[ -f "${INFRA}/env.revenue-island.example" ]]; then
    echo "No .env.revenue-island — copying from example. FILL SECRETS then re-run." >&2
    cp "${INFRA}/env.revenue-island.example" "$ENVF"
    exit 2
  fi
  echo "Missing $ENVF" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not installed. Wait for cloud-init or: curl -fsSL https://get.docker.com | sh" >&2
  exit 1
fi

cd "$INFRA"
echo "Pulling image (GHCR)..."
docker compose -f docker-compose.revenue-island.yml --env-file .env.revenue-island pull || true

echo "Starting postgres redis api worker worker_telegram worker_post beat (NO bots profile)..."
docker compose -f docker-compose.revenue-island.yml --env-file .env.revenue-island up -d postgres redis api worker worker_telegram worker_post beat

if [[ -x "${ROOT}/scripts/revenue-island/install-island-database-watchdog.sh" ]]; then
  echo "Installing database watchdog timer (postgres + redis every 5 min)..."
  bash "${ROOT}/scripts/revenue-island/install-island-database-watchdog.sh"
fi

echo ""
echo "OK: API plane up. Smoke: curl -fsS http://127.0.0.1:8000/health || true"
echo "Next: pg_dump restore + alembic (see docs/REVENUE_ISLAND.md)."
echo "Bots: only after home payment/loot stopped → up-island-bots.sh"
