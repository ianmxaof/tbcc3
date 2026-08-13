#!/usr/bin/env bash
# Expose island dashboard (+ optional forum) on the Tailscale tailnet via `tailscale serve`.
# Keeps docker binds on 127.0.0.1 — public IP stays closed; MagicDNS users get HTTPS on the node.
#
#   bash /opt/tbcc/scripts/revenue-island/enable-island-tailscale-serve.sh
set -euo pipefail

if ! command -v tailscale >/dev/null 2>&1; then
  echo "tailscale not installed" >&2
  exit 1
fi

# Reset previous serves for a clean slate
tailscale serve reset || true

# Dashboard on :443 of this node (https://tbcc-revenue-island / https://100.x)
tailscale serve --bg --https=443 http://127.0.0.1:5173

# Forum on :8443 of this node (https://tbcc-revenue-island:8443)
tailscale serve --bg --https=8443 http://127.0.0.1:3001

echo "=== tailscale serve status ==="
tailscale serve status || true
echo
echo "From a Tailscale-connected machine:"
echo "  Dashboard: https://$(tailscale status --json 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get(\"Self\",{}).get(\"DNSName\",\"tbcc-revenue-island\").rstrip(\".\"))' 2>/dev/null || echo tbcc-revenue-island)"
echo "  Forum:     https://tbcc-revenue-island:8443"
echo "  API (direct): http://tbcc-revenue-island:8000/health"
