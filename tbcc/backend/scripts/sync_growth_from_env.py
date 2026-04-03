"""
Apply tbcc/.env growth variables into growth_settings (row id=1).

Run from tbcc/backend:  python scripts/sync_growth_from_env.py

Use when you want the dashboard DB overrides to match .env exactly (e.g. after filling .env for testing).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# tbcc/backend
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from dotenv import load_dotenv

load_dotenv(_root.parent / ".env")

from app.database.session import SessionLocal
from app.models.growth_settings import GrowthSettings
from app.services.growth_settings_effective import ROW_ID


def _i(key: str) -> int | None:
    v = (os.getenv(key) or "").strip()
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _s(key: str) -> str | None:
    v = (os.getenv(key) or "").strip()
    return v or None


def main() -> None:
    db = SessionLocal()
    try:
        r = db.query(GrowthSettings).filter(GrowthSettings.id == ROW_ID).first()
        if not r:
            r = GrowthSettings(id=ROW_ID)
            db.add(r)
        r.landing_bulletin_chat_id = _s("TBCC_LANDING_BULLETIN_CHAT_ID")
        r.landing_bulletin_message_thread_id = _i("TBCC_LANDING_BULLETIN_MESSAGE_THREAD_ID")
        r.landing_bulletin_hour_utc = _i("TBCC_LANDING_BULLETIN_HOUR_UTC")
        r.landing_bulletin_bot_username = _s("TBCC_LANDING_BULLETIN_BOT_USERNAME") or _s("BOT_USERNAME")
        intro = (os.getenv("TBCC_LANDING_BULLETIN_INTRO") or "").strip()
        r.landing_bulletin_intro = intro or None
        r.referral_group_invite_link = _s("REFERRAL_GROUP_INVITE_LINK")
        r.referral_group_name = _s("REFERRAL_GROUP_NAME")
        rd = _i("REFERRAL_REWARD_DAYS")
        r.referral_reward_days = rd
        mode = (os.getenv("REFERRAL_MODE") or "").strip().lower()
        r.referral_mode = mode if mode in ("community", "premium") else None
        r.milestone_progress_chat_id = _s("MILESTONE_PROGRESS_CHAT_ID")
        db.commit()
        print("growth_settings row synced from .env (id=%s)." % ROW_ID)
    finally:
        db.close()


if __name__ == "__main__":
    main()
