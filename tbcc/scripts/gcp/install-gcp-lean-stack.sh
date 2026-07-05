#!/usr/bin/env bash
# Install TBCC lean Docker stack on a GCP (or any Linux) VPS.
# Run on the VM after repo is at /opt/tbcc (git clone or rsync from home).
set -euo pipefail

TBCC_ROOT="${TBCC_ROOT:-/opt/tbcc}"
REPO_DIR="${REPO_DIR:-$TBCC_ROOT}"
# Monorepo layout: telegram_bot2/tbcc — adjust if you clone only tbcc/
if [[ -d "$REPO_DIR/tbcc/infra" ]]; then
  TBCC_ROOT="$REPO_DIR/tbcc"
elif [[ -d "$REPO_DIR/infra" ]]; then
  TBCC_ROOT="$REPO_DIR"
else
  echo "Expected tbcc at $REPO_DIR or $REPO_DIR/tbcc"
  exit 1
fi

INFRA="$TBCC_ROOT/infra"
ENV_FILE="$INFRA/.env.gcp-lean"

echo "==> TBCC GCP lean stack install"
echo "    TBCC root: $TBCC_ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER" 2>/dev/null || true
  echo "Log out and back in for docker group, then re-run this script."
  exit 0
fi

mkdir -p "$INFRA/data/sessions" "$INFRA/data/media"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$INFRA/env.gcp-lean.example" "$ENV_FILE"
  echo "Created $ENV_FILE — set secrets before starting (or sync from home PC)."
fi

# Compose interpolates ${POSTGRES_PASSWORD} from shell when we source env
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

missing=0
for key in API_ID API_HASH POSTGRES_PASSWORD; do
  val="${!key:-}"
  if [[ -z "$val" || "$val" == CHANGE_ME_* ]]; then
    echo "MISSING or placeholder: $key in $ENV_FILE"
    missing=1
  fi
done

if [[ ! -f "$INFRA/data/sessions/admin.session" ]]; then
    echo "MISSING: $INFRA/data/sessions/admin.session"
    echo "  Re-run setup-tbcc-gcp.ps1 from home or sync-stack-to-gcp.ps1"
    missing=1
  fi
  if [[ ! -f "$INFRA/data/sessions/admin_poster.session" ]]; then
    echo "MISSING: $INFRA/data/sessions/admin_poster.session"
    missing=1
  fi

if [[ "$missing" -ne 0 ]]; then
  exit 1
fi

cd "$INFRA"
echo "==> Building images (first run may take several minutes)..."
docker compose -f docker-compose.gcp-lean.yml build

echo "==> Running migrations..."
docker compose -f docker-compose.gcp-lean.yml run --rm api python -m alembic upgrade head

echo "==> Starting lean stack..."
docker compose -f docker-compose.gcp-lean.yml up -d

echo ""
echo "Stack started. API bound to 127.0.0.1:8000 on this VM."
echo "  Health:  curl -s http://127.0.0.1:8000/health"
echo "  Logs:    docker compose -f docker-compose.gcp-lean.yml logs -f api celery"
echo "  Verify:  bash $TBCC_ROOT/scripts/gcp/health-gcp-stack.sh"
echo ""
echo "Expose API with Cloudflare Tunnel or Tailscale — do not open :8000 to 0.0.0.0 on the public internet."
