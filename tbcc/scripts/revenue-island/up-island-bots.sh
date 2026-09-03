#!/usr/bin/env bash
# Start island payment_bot + loot_bot + companion_bot after home bots are confirmed down.
# Run on a machine that can reach home Status (optional) and the island Docker host.
#
# Usage (from tbcc/infra on the VPS):
#   ../../scripts/revenue-island/up-island-bots.sh
# Optional: HOME_STATUS_CMD='ssh home-pc powershell ... assert-home-bots-down.ps1'

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INFRA="${ROOT}/infra"
COMPOSE="${INFRA}/docker-compose.revenue-island.yml"
ENVF="${INFRA}/.env.revenue-island"

if [[ ! -f "$COMPOSE" ]]; then
  echo "Missing $COMPOSE" >&2
  exit 1
fi
if [[ ! -f "$ENVF" ]]; then
  echo "Missing $ENVF — copy env.revenue-island.example" >&2
  exit 1
fi

if [[ -n "${HOME_STATUS_CMD:-}" ]]; then
  echo "Checking home bots via HOME_STATUS_CMD..."
  # shellcheck disable=SC2086
  eval $HOME_STATUS_CMD
else
  echo "WARN: HOME_STATUS_CMD unset — ensure home payment/loot are stopped before continuing."
  echo "      From home: powershell -File tbcc/scripts/revenue-island/assert-home-bots-down.ps1"
fi

cd "$INFRA"
docker compose -f docker-compose.revenue-island.yml --env-file .env.revenue-island --profile bots up -d payment_bot loot_bot companion_bot secretary_bot macro_search_bot
echo "Island bots up. Smoke: payment /start, loot /roll, @aof_spicybot_bot /start, @aof_secretary_bot /inbox; GET /companion/ops."
