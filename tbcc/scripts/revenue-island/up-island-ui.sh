#!/usr/bin/env bash
# Start always-on dashboard + AOF Forum on the revenue island (compose profile ui).
# Prefers GHCR images; falls back to --build if pull fails.
set -euo pipefail
ROOT="${TBCC_ISLAND_ROOT:-/opt/tbcc}"
cd "$ROOT/infra"
export AOF_FORUM_BUILD_CONTEXT="${AOF_FORUM_BUILD_CONTEXT:-/opt/aof-forum}"
COMPOSE=(docker compose -f docker-compose.revenue-island.yml --env-file .env.revenue-island --profile ui)

echo "Pulling UI images (GHCR)..."
"${COMPOSE[@]}" pull dashboard forum || echo "pull failed — will build locally if needed"

echo "Bringing up dashboard + forum..."
if ! "${COMPOSE[@]}" up -d --no-build dashboard forum; then
  echo "up without build failed — building..."
  "${COMPOSE[@]}" up -d --build dashboard forum
fi
"${COMPOSE[@]}" ps dashboard forum
echo "Local binds: dash http://127.0.0.1:5173  forum http://127.0.0.1:3001"
echo "Public: https://dash.powercore.app  https://forum.powercore.app"
echo "Enable Cloudflare Zero Trust Access on dash.* (injects API key — do not leave open)."
