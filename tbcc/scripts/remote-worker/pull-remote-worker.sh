#!/usr/bin/env bash
# Pull latest GHCR worker image and recreate containers (no local build).
set -euo pipefail

TBCC_ROOT="${TBCC_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
INFRA="$TBCC_ROOT/infra"
GHCR_IMAGE="${TBCC_WORKER_IMAGE:-ghcr.io/ianmxaof/tbcc-worker:latest}"
COMPOSE="$INFRA/docker-compose.remote-worker.ghcr.yml"

cd "$INFRA"
export TBCC_WORKER_IMAGE="$GHCR_IMAGE"

if [[ -n "${TBCC_GHCR_TOKEN:-}" && -n "${TBCC_GHCR_USER:-}" ]]; then
  echo "$TBCC_GHCR_TOKEN" | docker login ghcr.io -u "$TBCC_GHCR_USER" --password-stdin
fi

echo "==> Pulling $GHCR_IMAGE"
docker compose -f "$COMPOSE" pull
echo "==> Recreating workers"
docker compose -f "$COMPOSE" up -d --force-recreate
echo "OK — logs: docker compose -f $COMPOSE logs -f worker_scrape"
