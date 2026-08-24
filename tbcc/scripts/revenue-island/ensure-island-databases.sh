#!/usr/bin/env bash
# Ensure Postgres + Redis on revenue island are running and accepting connections.
# Safe for cron/systemd timer — starts or recreates DB containers if stopped/unhealthy.
#
# Usage on VPS:
#   bash /opt/tbcc/scripts/revenue-island/ensure-island-databases.sh
#   bash ensure-island-databases.sh --restart-api   # also bounce api if DB was recovered

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INFRA="${ROOT}/infra"
COMPOSE_FILE="docker-compose.revenue-island.yml"
ENV_FILE=".env.revenue-island"
RESTART_API=0

for arg in "$@"; do
  case "$arg" in
    --restart-api) RESTART_API=1 ;;
  esac
done

cd "$INFRA"

if [[ ! -f "$COMPOSE_FILE" || ! -f "$ENV_FILE" ]]; then
  echo "ensure-island-databases: missing compose or $ENV_FILE" >&2
  exit 1
fi

# Redis requires auth (requirepass) — pull the password straight out of the env
# file rather than `source`-ing it, so a literal `$` in the value can't be
# misread as shell expansion.
TBCC_REDIS_PASSWORD="$(grep -m1 '^TBCC_REDIS_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)"

compose() {
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

service_running() {
  local svc="$1"
  compose ps --status running -q "$svc" 2>/dev/null | grep -q .
}

postgres_ok() {
  service_running postgres && compose exec -T postgres pg_isready -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-tbcc}" >/dev/null 2>&1
}

redis_ok() {
  service_running redis && compose exec -T redis redis-cli --no-auth-warning -a "$TBCC_REDIS_PASSWORD" ping 2>/dev/null | grep -q PONG
}

ensure_service() {
  local svc="$1"
  local ok_fn="$2"
  if "$ok_fn"; then
    echo "ensure-island-databases: $svc OK"
    return 0
  fi
  echo "ensure-island-databases: $svc unhealthy or stopped — starting..."
  compose up -d "$svc"
  for _ in $(seq 1 30); do
    if "$ok_fn"; then
      echo "ensure-island-databases: $svc recovered"
      return 0
    fi
    sleep 2
  done
  echo "ensure-island-databases: $svc still unhealthy after start" >&2
  return 1
}

db_recovered=0
if ! postgres_ok; then
  ensure_service postgres postgres_ok || exit 1
  db_recovered=1
fi
if ! redis_ok; then
  ensure_service redis redis_ok || exit 1
  db_recovered=1
fi

if [[ "$RESTART_API" -eq 1 && "$db_recovered" -eq 1 ]]; then
  echo "ensure-island-databases: restarting api after DB recovery..."
  compose restart api || true
fi

postgres_ok && redis_ok
echo "ensure-island-databases: OK"
