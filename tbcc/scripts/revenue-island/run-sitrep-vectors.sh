#!/usr/bin/env bash
# Sitrep vectors 1,2,4,5 on revenue island. Run on VPS:
#   bash /opt/tbcc/scripts/revenue-island/run-sitrep-vectors.sh
set -euo pipefail
cd /opt/tbcc/infra
COMPOSE="docker compose -f docker-compose.revenue-island.yml --env-file .env.revenue-island"
API="$COMPOSE exec -T api"

echo "=== [1] Alembic + prompt_gate import/provision + goblin apply ==="
$API alembic upgrade head
$API python scripts/provision_prompt_gates.py --import-json app/data/prompt_gate_catalog.sample.json || true
$API python scripts/provision_prompt_gates.py --status || true
# Provision only if queue pending and selectors ready (skip if no auth)
if $API python scripts/provision_prompt_gates.py --status 2>/dev/null | grep -q 'pending=1'; then
  $API python scripts/provision_prompt_gates.py --execute --key goblin_boombox_v1 || echo "WARN: island LV provision skipped (auth/selectors)"
fi
# Fallback: copy known home slug if row still pending (avoid split-brain re-provision)
$API python - <<'PY' || true
from app.database.session import SessionLocal
from app.models.prompt_gate import PROMPT_GATE_STATUS_PENDING, PROMPT_GATE_STATUS_PROVISIONED, PromptGate
from app.services.prompt_gate_lookup import hash_prompt_body

SLUG = "https://link-target.net/1367336/5TBnuCOM8Zfq"
BODY = "SFW AOF Loot Goblin boombox teleport scene. Red cyberpunk Genesis-cover mood. Empty magenta center for card chrome. No baked text."
db = SessionLocal()
try:
    row = db.query(PromptGate).filter(PromptGate.key == "goblin_boombox_v1").order_by(PromptGate.id.desc()).first()
    if row and row.status == PROMPT_GATE_STATUS_PENDING and not (row.lv_url or "").strip():
        row.lv_url = SLUG
        row.status = PROMPT_GATE_STATUS_PROVISIONED
        row.body_hash = row.body_hash or hash_prompt_body(BODY)
        db.commit()
        print("fallback_slug_applied", SLUG)
    elif row and row.status == PROMPT_GATE_STATUS_PROVISIONED:
        print("already_provisioned", row.lv_url)
    else:
        print("no_fallback_needed", getattr(row, "status", None))
finally:
    db.close()
PY
$API python scripts/apply_goblin_milestone_promo.py --execute --sync-network --skip-milestone || true

echo "=== [2] Pin goblin bulletin (photo + caption) ==="
$API python - <<'PY'
import json
from pathlib import Path
from app.database.session import SessionLocal
from app.data.aof_network import MAIN_GROUP_IDENT
from app.services.aof_loot_goblin_promo import (
    build_loot_room_goblin_bulletin_html,
    channel_id_for_ident,
    LOOT_ROOM_GOBLIN_BULLETIN_NAME,
)
from app.models.scheduled_text_post import ScheduledTextPost
from app.workers.poster_worker import post_scheduled_text

img = Path("docs/samples/loot_goblin_lrg_reference_grid.png")
if not img.is_file():
    img = Path("/opt/tbcc/backend/docs/samples/loot_goblin_lrg_reference_grid.png")
caption = build_loot_room_goblin_bulletin_html()
db = SessionLocal()
try:
    cid = channel_id_for_ident(db, MAIN_GROUP_IDENT)
    if not cid:
        print(json.dumps({"ok": False, "error": "loot_room_channel_missing"}))
        raise SystemExit(1)
    sched = (
        db.query(ScheduledTextPost)
        .filter(
            ScheduledTextPost.channel_id == cid,
            ScheduledTextPost.name == LOOT_ROOM_GOBLIN_BULLETIN_NAME,
        )
        .first()
    )
    if not sched:
        sched = ScheduledTextPost(
            name=LOOT_ROOM_GOBLIN_BULLETIN_NAME,
            channel_id=cid,
            content=caption,
            pin_after_send=True,
            send_silent=False,
            scheduler_category="promo_bulletin",
        )
        db.add(sched)
        db.flush()
    else:
        sched.content = caption
        sched.pin_after_send = True
        sched.sent_at = None
    if img.is_file():
        promo_dir = Path("static/promo")
        promo_dir.mkdir(parents=True, exist_ok=True)
        dest = promo_dir / "loot_goblin_lrg_reference_grid.png"
        dest.write_bytes(img.read_bytes())
        sched.attachment_urls_json = json.dumps(["/static/promo/loot_goblin_lrg_reference_grid.png"])
    db.commit()
    post_scheduled_text(int(sched.id), manual_trigger=True)
    print(json.dumps({"ok": True, "post_id": sched.id, "image": str(img), "pinned": True}))
finally:
    db.close()
PY

echo "=== [4] Goblin spawn smoke (recent drops) ==="
$API python - <<'PY'
import json
from datetime import datetime, timedelta, timezone
from app.database.session import SessionLocal
from app.models.goblin_drop import GoblinDrop
from app.models.listening_relay_settings import ListeningRelaySettings

db = SessionLocal()
try:
    since = datetime.now(timezone.utc) - timedelta(days=3)
    drops = (
        db.query(GoblinDrop)
        .filter(GoblinDrop.created_at >= since)
        .order_by(GoblinDrop.id.desc())
        .limit(5)
        .all()
    )
    row = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == 1).first()
    out = {
        "goblin_mode_enabled": bool(getattr(row, "goblin_mode_enabled", False)),
        "spawn_chance": float(getattr(row, "goblin_spawn_chance", 0) or 0),
        "spawns_today": int(getattr(row, "goblin_spawns_today", 0) or 0),
        "recent_drops": [
            {
                "id": d.id,
                "channel_id": d.channel_id,
                "status": d.status,
                "created_at": str(d.created_at),
            }
            for d in drops
        ],
    }
    print(json.dumps(out, indent=2))
finally:
    db.close()
PY

echo "=== [5] Pool album dedupe audit ASS + ABG ==="
$API python scripts/audit_pool_album_duplicates.py --pool "AOF ASS POOL" || true
$API python scripts/audit_pool_album_duplicates.py --pool "ABG / LBFM POOL" || true

echo "=== DONE ==="
