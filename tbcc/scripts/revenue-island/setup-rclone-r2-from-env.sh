#!/usr/bin/env bash
# Configure rclone remote `r2` from env (S3 API). Never echoes secrets.
# Required:
#   TBCC_R2_ACCOUNT_ID
#   TBCC_R2_ACCESS_KEY_ID
#   TBCC_R2_SECRET_ACCESS_KEY
# Optional:
#   TBCC_R2_BUCKET (default aof-media)
#   TBCC_R2_S3_ENDPOINT
set -euo pipefail

ACCOUNT_ID="${TBCC_R2_ACCOUNT_ID:?TBCC_R2_ACCOUNT_ID required}"
ACCESS_KEY="${TBCC_R2_ACCESS_KEY_ID:?TBCC_R2_ACCESS_KEY_ID required}"
SECRET_KEY="${TBCC_R2_SECRET_ACCESS_KEY:?TBCC_R2_SECRET_ACCESS_KEY required}"
BUCKET="${TBCC_R2_BUCKET:-aof-media}"
ENDPOINT="${TBCC_R2_S3_ENDPOINT:-}"
if [[ -z "$ENDPOINT" ]]; then
  ENDPOINT="https://${ACCOUNT_ID}.r2.cloudflarestorage.com"
fi

mkdir -p /root/.config/rclone
# Drop any prior [r2] section, then append fresh
CONF="/root/.config/rclone/rclone.conf"
if [[ -f "$CONF" ]]; then
  awk '
    BEGIN{skip=0}
    /^\[/{skip=($0=="[r2]")}
    !skip{print}
  ' "$CONF" > "${CONF}.tmp" && mv "${CONF}.tmp" "$CONF"
fi

cat >> "$CONF" <<EOF
[r2]
type = s3
provider = Cloudflare
access_key_id = ${ACCESS_KEY}
secret_access_key = ${SECRET_KEY}
endpoint = ${ENDPOINT}
acl = private
no_check_bucket = true
EOF

chmod 600 "$CONF"
echo "rclone r2 remote configured (endpoint host only): ${ENDPOINT%%/*}//${ENDPOINT#*//}"
echo "smoke: rclone lsd r2:${BUCKET}"
rclone lsd "r2:${BUCKET}" --max-depth 1 2>&1 | head -20
rclone mkdir "r2:${BUCKET}/mega-export" 2>/dev/null || true
echo "OK r2:${BUCKET}/mega-export ready"
