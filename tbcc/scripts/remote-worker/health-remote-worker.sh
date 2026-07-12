#!/usr/bin/env bash
# Ping Redis + Postgres + Celery scrape worker from the remote VM.
set -euo pipefail

TBCC_ROOT="${TBCC_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
INFRA="$TBCC_ROOT/infra"
ENV_FILE="$INFRA/.env.remote-worker"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE"
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

pick_compose() {
  if docker compose -f "$INFRA/docker-compose.remote-worker.ghcr.yml" ps --status running 2>/dev/null | grep -q worker_scrape; then
    echo "$INFRA/docker-compose.remote-worker.ghcr.yml"
  elif [[ -f "$INFRA/docker-compose.remote-worker.ghcr.yml" ]] && [[ "${TBCC_USE_GHCR:-0}" == "1" ]]; then
    echo "$INFRA/docker-compose.remote-worker.ghcr.yml"
  else
    echo "$INFRA/docker-compose.remote-worker.yml"
  fi
}

COMPOSE="$(pick_compose)"

echo "==> Redis"
docker run --rm --network host redis:7-alpine redis-cli -u "${REDIS_URL}" ping

echo "==> Postgres"
docker run --rm --network host -e DATABASE_URL="$DATABASE_URL" \
  python:3.12-slim bash -c '
    pip -q install psycopg2-binary sqlalchemy >/dev/null
    python -c "
import os
from sqlalchemy import create_engine, text
e = create_engine(os.environ[\"DATABASE_URL\"])
with e.connect() as c:
    print(\"sources:\", c.execute(text(\"select count(*) from sources\")).scalar())
"'

echo "==> Celery scrape worker ($COMPOSE)"
cd "$INFRA"
docker compose -f "$COMPOSE" exec -T worker_scrape \
  celery -A app.workers.celery_app inspect ping -d scrape@remote 2>/dev/null || \
  echo "(worker not running or still starting)"

echo "==> Session file"
ls -la "$INFRA/data/sessions/scraper.session" 2>/dev/null || echo "scraper.session missing"

echo "OK"
