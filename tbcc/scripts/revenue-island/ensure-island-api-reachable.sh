#!/usr/bin/env bash
# Ensure island API responds locally and the public tunnel is up.
# Safe to run from deploy, cron, or manually after dashboard shows api_unreachable.
#
# Usage on VPS:
#   bash /opt/tbcc/scripts/revenue-island/ensure-island-api-reachable.sh
#   bash ensure-island-api-reachable.sh --public-check   # also curl TBCC_PUBLIC_API_BASE_URL

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INFRA="${ROOT}/infra"
COMPOSE_FILE="docker-compose.revenue-island.yml"
ENV_FILE=".env.revenue-island"
SERVICE="cloudflared-tbcc-api"
HEALTH_URL="http://127.0.0.1:8000/health"
TIMEOUT_S="${TBCC_ISLAND_HEALTH_TIMEOUT_S:-8}"
PUBLIC_CHECK=0

for arg in "$@"; do
  case "$arg" in
    --public-check) PUBLIC_CHECK=1 ;;
  esac
done

cd "$INFRA"

if [[ -x "${ROOT}/scripts/revenue-island/ensure-island-databases.sh" ]]; then
  bash "${ROOT}/scripts/revenue-island/ensure-island-databases.sh" || {
    echo "ensure-island-api: database ensure failed — aborting API check" >&2
    exit 1
  }
fi

health_ok() {
  curl -fsS --max-time "$TIMEOUT_S" "$HEALTH_URL" >/dev/null 2>&1
}

restart_api() {
  echo "ensure-island-api: restarting api container..."
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" restart api
  for _ in $(seq 1 20); do
    if health_ok; then
      return 0
    fi
    sleep 2
  done
  echo "ensure-island-api: api still unhealthy after restart" >&2
  return 1
}

ensure_tunnel() {
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "ensure-island-api: systemctl missing — skip tunnel check" >&2
    return 0
  fi
  if systemctl is-active --quiet "$SERVICE"; then
    echo "ensure-island-api: $SERVICE active"
    return 0
  fi
  echo "ensure-island-api: starting $SERVICE..."
  systemctl start "$SERVICE" || systemctl restart "$SERVICE"
  sleep 2
  if systemctl is-active --quiet "$SERVICE"; then
    echo "ensure-island-api: $SERVICE started"
    return 0
  fi
  echo "ensure-island-api: $SERVICE failed to start — check journalctl -u $SERVICE" >&2
  return 1
}

if health_ok; then
  echo "ensure-island-api: local health OK"
else
  echo "ensure-island-api: local health failed (timeout ${TIMEOUT_S}s)"
  restart_api
fi

ensure_tunnel

if [[ "$PUBLIC_CHECK" -eq 1 ]]; then
  PUBLIC_BASE=""
  if [[ -f "$INFRA/.env.revenue-island" ]]; then
    PUBLIC_BASE="$(grep -E '^TBCC_PUBLIC_API_BASE_URL=' "$INFRA/.env.revenue-island" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '\r' | xargs)"
  fi
  if [[ -z "$PUBLIC_BASE" && -f "$INFRA/.api-public-url" ]]; then
    PUBLIC_BASE="$(grep -E '^TBCC_PUBLIC_API_BASE_URL=' "$INFRA/.api-public-url" | head -1 | cut -d= -f2- | tr -d '\r' | xargs)"
  fi
  if [[ -n "$PUBLIC_BASE" ]]; then
    echo "ensure-island-api: public check $PUBLIC_BASE/health"
    curl -fsS --max-time 20 "${PUBLIC_BASE%/}/health" || {
      echo "ensure-island-api: public URL not reachable yet — tunnel may need a minute" >&2
      exit 1
    }
  fi
fi

curl -fsS --max-time "$TIMEOUT_S" "$HEALTH_URL"
echo ""
echo "ensure-island-api: OK"
