#!/usr/bin/env bash
# Cloudflare quick tunnel → HTTPS public URL for Gumroad Ping + NOWPayments IPN.
# URL is written to /opt/tbcc/infra/.api-public-url (stable until cloudflared restarts).
#
# Usage on VPS:
#   bash /opt/tbcc/scripts/revenue-island/install-island-api-tunnel.sh
#   source /opt/tbcc/infra/.api-public-url   # TBCC_PUBLIC_API_BASE_URL=...

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INFRA="${ROOT}/infra"
URL_FILE="${INFRA}/.api-public-url"
ENVF="${INFRA}/.env.revenue-island"
SERVICE="cloudflared-tbcc-api"
LOG="/var/log/cloudflared-tbcc-api.log"

install_cloudflared() {
  if command -v cloudflared >/dev/null 2>&1; then
    return 0
  fi
  echo "Installing cloudflared..."
  curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb \
    -o /tmp/cloudflared.deb
  dpkg -i /tmp/cloudflared.deb || apt-get install -f -y
  rm -f /tmp/cloudflared.deb
}

write_systemd() {
  cat >"/etc/systemd/system/${SERVICE}.service" <<EOF
[Unit]
Description=TBCC API Cloudflare quick tunnel (Gumroad/NOWPayments webhooks)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8000
Restart=always
RestartSec=5
StandardOutput=append:${LOG}
StandardError=append:${LOG}

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable "${SERVICE}"
  systemctl restart "${SERVICE}"
}

wait_for_url() {
  local url=""
  for _ in $(seq 1 45); do
    if [[ -f "$LOG" ]]; then
      url="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1 || true)"
      if [[ -n "$url" ]]; then
        echo "$url"
        return 0
      fi
    fi
    sleep 2
  done
  echo "Timed out waiting for trycloudflare URL — check: journalctl -u ${SERVICE} -n 50" >&2
  return 1
}

patch_env() {
  local base="$1"
  if [[ ! -f "$ENVF" ]]; then
    echo "Missing $ENVF" >&2
    return 1
  fi
  for key in TBCC_PUBLIC_API_BASE_URL TBCC_API_PUBLIC_URL; do
    if grep -q "^${key}=" "$ENVF"; then
      sed -i "s|^${key}=.*|${key}=${base}|" "$ENVF"
    else
      echo "${key}=${base}" >>"$ENVF"
    fi
  done
}

install_cloudflared
mkdir -p "$INFRA"
: >"$LOG"
write_systemd

PUBLIC_URL="$(wait_for_url)"
echo "TBCC_PUBLIC_API_BASE_URL=${PUBLIC_URL}" >"$URL_FILE"
echo "TBCC_API_PUBLIC_URL=${PUBLIC_URL}" >>"$URL_FILE"
patch_env "$PUBLIC_URL"

echo ""
echo "OK: public API base = ${PUBLIC_URL}"
echo "    Written to ${URL_FILE} and patched ${ENVF}"
echo "    Recreate api/payment_bot after env change:"
echo "      cd ${INFRA} && docker compose -f docker-compose.revenue-island.yml --env-file .env.revenue-island --profile bots up -d --force-recreate api payment_bot worker worker_post beat"
