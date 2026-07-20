#!/usr/bin/env bash
# Named Cloudflare tunnel -> stable hostname (e.g. api.powercore.app).
# Requires one-time: cloudflared tunnel login (opens browser) OR CF_TUNNEL_TOKEN env.
#
# Usage:
#   CF_HOSTNAME=api.powercore.app bash install-island-named-tunnel.sh
#   CF_TUNNEL_TOKEN=eyJ... CF_HOSTNAME=api.powercore.app bash install-island-named-tunnel.sh
#
# Before DNS: point hostname CNAME to <tunnel-id>.cfargotunnel.com in Cloudflare DNS
# (script can add route when logged in: cloudflared tunnel route dns tbcc-api $CF_HOSTNAME)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INFRA="${ROOT}/infra"
ENVF="${INFRA}/.env.revenue-island"
URL_FILE="${INFRA}/.api-public-url"
TUNNEL_NAME="${CF_TUNNEL_NAME:-tbcc-api}"
HOSTNAME="${CF_HOSTNAME:-api.powercore.app}"
SERVICE="cloudflared-tbcc-api"

if ! command -v cloudflared >/dev/null 2>&1; then
  curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb
  dpkg -i /tmp/cloudflared.deb || apt-get install -f -y
  rm -f /tmp/cloudflared.deb
fi

mkdir -p /etc/cloudflared
CONFIG="/etc/cloudflared/config.yml"

if [[ -n "${CF_TUNNEL_TOKEN:-}" ]]; then
  cat >"/etc/systemd/system/${SERVICE}.service" <<EOF
[Unit]
Description=TBCC API Cloudflare named tunnel ($HOSTNAME)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/cloudflared tunnel --no-autoupdate run --token ${CF_TUNNEL_TOKEN}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
else
  if ! cloudflared tunnel list 2>/dev/null | grep -q "$TUNNEL_NAME"; then
    echo "Create tunnel (login required if first time):" >&2
    cloudflared tunnel create "$TUNNEL_NAME"
  fi
  TUNNEL_ID="$(cloudflared tunnel list | awk -v n="$TUNNEL_NAME" '$0 ~ n {print $1; exit}')"
  CRED="/root/.cloudflared/${TUNNEL_ID}.json"
  cat >"$CONFIG" <<EOF
tunnel: ${TUNNEL_ID}
credentials-file: ${CRED}
ingress:
  - hostname: ${HOSTNAME}
    service: http://127.0.0.1:8000
  - service: http_status:404
EOF
  cloudflared tunnel route dns "$TUNNEL_NAME" "$HOSTNAME" || echo "DNS route may need manual CNAME in Cloudflare dashboard" >&2
  cat >"/etc/systemd/system/${SERVICE}.service" <<EOF
[Unit]
Description=TBCC API Cloudflare named tunnel ($HOSTNAME)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/cloudflared tunnel --no-autoupdate --config ${CONFIG} run ${TUNNEL_NAME}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
fi

systemctl daemon-reload
systemctl enable "${SERVICE}"
systemctl restart "${SERVICE}"

BASE="https://${HOSTNAME}"
for key in TBCC_PUBLIC_API_BASE_URL TBCC_API_PUBLIC_URL; do
  if grep -q "^${key}=" "$ENVF"; then
    sed -i "s|^${key}=.*|${key}=${BASE}|" "$ENVF"
  else
    echo "${key}=${BASE}" >>"$ENVF"
  fi
done
echo "TBCC_PUBLIC_API_BASE_URL=${BASE}" >"$URL_FILE"
echo "TBCC_API_PUBLIC_URL=${BASE}" >>"$URL_FILE"

echo ""
echo "OK: stable API base = ${BASE}"
echo "Recreate api + payment_bot after env change."
echo "Re-wire Gumroad Ping + NOWPayments IPN to:"
echo "  ${BASE}/webhooks/gumroad"
echo "  ${BASE}/webhooks/nowpayments"
