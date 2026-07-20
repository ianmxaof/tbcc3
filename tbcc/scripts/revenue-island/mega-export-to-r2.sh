#!/usr/bin/env bash
# Server-side Mega → R2 copy (run on revenue island). Streams via rclone; no local vault.
# Usage:
#   ./mega-export-to-r2.sh              # start / resume copy in background
#   ./mega-export-to-r2.sh --dry-run
#   ./mega-export-to-r2.sh --status
#   ./mega-export-to-r2.sh --foreground
set -euo pipefail

BUCKET="${TBCC_R2_BUCKET:-aof-media}"
SRC="${MEGA_RCLONE_SRC:-mega:}"
DST="r2:${BUCKET}/mega-export"
LOG_DIR="${TBCC_MEGA_R2_LOG_DIR:-/var/log/tbcc}"
LOG="${LOG_DIR}/mega-export-to-r2.log"
PIDFILE="${LOG_DIR}/mega-export-to-r2.pid"
MODE="${1:-}"

mkdir -p "$LOG_DIR"

rclone_flags=(
  copy "$SRC" "$DST"
  --progress
  --stats 30s
  --stats-log-level NOTICE
  --transfers 4
  --checkers 8
  --retries 5
  --low-level-retries 10
  --mega-hard-delete=false
  --fast-list
)

status() {
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "RUNNING pid=$(cat "$PIDFILE")"
  else
    echo "NOT_RUNNING"
  fi
  echo "log=$LOG"
  if [[ -f "$LOG" ]]; then
    tail -n 30 "$LOG" || true
  fi
  echo "--- remote sizes (may be slow) ---"
  rclone size "$SRC" 2>&1 | tail -5 || true
  rclone size "$DST" 2>&1 | tail -5 || true
}

if [[ "$MODE" == "--status" ]]; then
  status
  exit 0
fi

if [[ "$MODE" == "--dry-run" ]]; then
  echo "DRY-RUN $SRC -> $DST"
  rclone "${rclone_flags[@]}" --dry-run 2>&1 | tee -a "$LOG"
  exit 0
fi

# Ensure remotes exist
rclone listremotes | grep -qx 'mega:' || { echo "missing mega: remote"; exit 1; }
rclone listremotes | grep -qx 'r2:' || { echo "missing r2: remote — run setup-rclone-r2-from-env.sh first"; exit 1; }
rclone lsd "r2:${BUCKET}" >/dev/null
rclone mkdir "$DST" 2>/dev/null || true

if [[ "$MODE" == "--foreground" ]]; then
  echo "FOREGROUND $SRC -> $DST"
  exec rclone "${rclone_flags[@]}" 2>&1 | tee -a "$LOG"
fi

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Already running pid=$(cat "$PIDFILE") — use --status"
  exit 0
fi

echo "BACKGROUND $SRC -> $DST"
nohup rclone "${rclone_flags[@]}" >>"$LOG" 2>&1 &
echo $! >"$PIDFILE"
echo "started pid=$(cat "$PIDFILE") log=$LOG"
echo "monitor: $0 --status"
