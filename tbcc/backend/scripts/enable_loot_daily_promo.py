"""One-shot: persist daily promo settings from tbcc/.env into loot_bot_settings row."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_tbcc = Path(__file__).resolve().parents[2]
load_dotenv(_tbcc / ".env", override=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.loot_bot_settings import _ensure_row
from app.database.session import SessionLocal
from app.services.loot_bot_settings_effective import (
    get_effective_loot_bot_settings,
    is_valid_telegram_bot_token,
)


def main() -> int:
    chat_raw = (os.getenv("TBCC_LOOT_AOF_GROUP_CHAT_ID") or "").strip()
    if not chat_raw:
        print("Set TBCC_LOOT_AOF_GROUP_CHAT_ID in tbcc/.env", file=sys.stderr)
        return 1
    try:
        chat_id = int(chat_raw)
    except ValueError:
        print("TBCC_LOOT_AOF_GROUP_CHAT_ID must be an integer", file=sys.stderr)
        return 1
    hour_raw = (os.getenv("TBCC_LOOT_DAILY_PROMO_HOUR_UTC") or "18").strip()
    try:
        hour = max(0, min(23, int(hour_raw)))
    except ValueError:
        hour = 18

    db = SessionLocal()
    try:
        r = _ensure_row(db)
        r.aof_group_chat_id = chat_id
        r.daily_promo_enabled = True
        r.daily_promo_hour_utc = hour
        env_buf = (os.getenv("TBCC_LOOT_BUFFER_MIRROR_ENABLED") or "").strip().lower()
        if env_buf in ("1", "true", "yes", "on"):
            r.buffer_mirror_enabled = True
        env_now = (os.getenv("TBCC_LOOT_BUFFER_PUBLISH_NOW") or "").strip().lower()
        if env_now in ("1", "true", "yes", "on"):
            r.buffer_publish_now = True
        if (r.bot_token or "").strip() and not is_valid_telegram_bot_token(r.bot_token):
            print("clearing invalid dashboard bot_token (use BotFather token, not internal API key)")
            r.bot_token = None
        db.commit()
        eff = get_effective_loot_bot_settings(db)
        print("daily_promo_enabled:", eff.get("daily_promo_enabled"))
        print("aof_group_chat_id:", eff.get("aof_group_chat_id"))
        print("daily_promo_hour_utc:", eff.get("daily_promo_hour_utc"))
        print("bot_token_configured:", eff.get("bot_token_configured"))
        print("buffer_mirror_enabled:", eff.get("buffer_mirror_enabled"))
        print("buffer_publish_now:", eff.get("buffer_publish_now"))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
