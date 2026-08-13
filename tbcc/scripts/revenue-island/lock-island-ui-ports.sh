#!/usr/bin/env bash
# Restrict published UI ports to localhost + Tailscale CGNAT (100.64.0.0/10).
# Safe companion to compose binding 0.0.0.0:5173 / :3001 for MagicDNS access.
set -euo pipefail

allow_port() {
  local port="$1"
  iptables -C INPUT -p tcp --dport "$port" -s 127.0.0.1 -j ACCEPT 2>/dev/null || \
    iptables -I INPUT -p tcp --dport "$port" -s 127.0.0.1 -j ACCEPT
  iptables -C INPUT -p tcp --dport "$port" -s 100.64.0.0/10 -j ACCEPT 2>/dev/null || \
    iptables -I INPUT -p tcp --dport "$port" -s 100.64.0.0/10 -j ACCEPT
  # Drop everyone else (public VPS IP) for this port
  iptables -C INPUT -p tcp --dport "$port" -j DROP 2>/dev/null || \
    iptables -A INPUT -p tcp --dport "$port" -j DROP
}

allow_port 5173
allow_port 3001
echo "UI ports 5173/3001: allow localhost + Tailscale only"
iptables -L INPUT -n | grep -E '5173|3001' || true
echo "Tailscale dash: http://$(tailscale ip -4):5173  or http://tbcc-revenue-island:5173"
echo "Optional HTTPS Serve (one-time enable): https://login.tailscale.com/f/serve?node=nJARcTxvJM11CNTRL"
