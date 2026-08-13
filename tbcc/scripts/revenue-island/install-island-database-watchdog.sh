#!/usr/bin/env bash
# Install systemd timer: keep island Postgres + Redis up (every 5 min + after boot).
#
# Usage on VPS:
#   bash /opt/tbcc/scripts/revenue-island/install-island-database-watchdog.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENSURE="${ROOT}/scripts/revenue-island/ensure-island-databases.sh"
SERVICE="tbcc-island-databases"
TIMER="${SERVICE}.timer"

if [[ ! -f "$ENSURE" ]]; then
  echo "Missing $ENSURE" >&2
  exit 1
fi

chmod +x "$ENSURE"
sed -i 's/\r$//' "$ENSURE" 2>/dev/null || true

cat >"/etc/systemd/system/${SERVICE}.service" <<EOF
[Unit]
Description=TBCC revenue island — ensure Postgres + Redis are up
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/bash ${ENSURE} --restart-api
EOF

cat >"/etc/systemd/system/${TIMER}" <<EOF
[Unit]
Description=TBCC island database watchdog (every 5 min)

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=1min
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now "${TIMER}"
systemctl start "${SERVICE}.service" || true

echo "Installed ${TIMER} — status:"
systemctl status "${TIMER}" --no-pager -l || true
echo ""
echo "Run once: systemctl start ${SERVICE}.service"
echo "Logs: journalctl -u ${SERVICE}.service -n 30"
