#!/usr/bin/env bash
# Health check for TBCC GCP lean stack.
set -euo pipefail

TBCC_ROOT="${TBCC_ROOT:-/opt/tbcc}"
if [[ -d "$TBCC_ROOT/tbcc/infra" ]]; then
  TBCC_ROOT="$TBCC_ROOT/tbcc"
fi
INFRA="$TBCC_ROOT/infra"
ENV_FILE="$INFRA/.env.gcp-lean"
COMPOSE="docker compose -f docker-compose.gcp-lean.yml"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE"
  exit 1
fi

cd "$INFRA"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

echo "==> API"
curl -sf http://127.0.0.1:8000/health | head -c 200
echo ""

echo "==> Postgres"
$COMPOSE exec -T postgres psql -U postgres -d tbcc -c "select count(*) as sources from sources;" 2>/dev/null || echo "(postgres query failed)"

echo "==> Redis"
$COMPOSE exec -T redis redis-cli ping

echo "==> Celery workers"
$COMPOSE exec -T celery celery -A app.workers.celery_app inspect ping -d celery@gcp 2>/dev/null || echo "(celery@gcp not responding yet)"
$COMPOSE exec -T celery_post celery -A app.workers.celery_app inspect ping -d post@gcp 2>/dev/null || echo "(post@gcp not responding yet)"

echo "==> Sessions"
ls -la "$INFRA/data/sessions/"*.session 2>/dev/null | head -10 || echo "(no .session files)"

echo "OK"
