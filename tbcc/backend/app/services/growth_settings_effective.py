"""
Merged growth/referral settings: DB row id=1 overrides env when column is non-null.

Workers and payment bot use this so the dashboard can edit without redeploying .env.
"""
from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

from app.models.growth_settings import GrowthSettings

ROW_ID = 1


def _row(db: Session) -> GrowthSettings | None:
    return db.query(GrowthSettings).filter(GrowthSettings.id == ROW_ID).first()


def _str_or_env(db_val: object | None, env_key: str, default: str = "") -> str:
    if db_val is not None and str(db_val).strip() != "":
        return str(db_val).strip()
    return (os.getenv(env_key) or default).strip()


def _int_or_env(db_val: object | None, env_key: str, default: int) -> int:
    if db_val is not None:
        try:
            return int(db_val)
        except (TypeError, ValueError):
            pass
    raw = os.getenv(env_key)
    if raw is not None and str(raw).strip() != "":
        try:
            return int(raw)
        except ValueError:
            pass
    return default


def get_effective_growth_settings(db: Session) -> dict[str, Any]:
    """All keys used by workers, growth_promo, and payment bot."""
    r = _row(db)
    hour = _int_or_env(
        getattr(r, "landing_bulletin_hour_utc", None) if r else None,
        "TBCC_LANDING_BULLETIN_HOUR_UTC",
        14,
    )
    reward_days = _int_or_env(
        getattr(r, "referral_reward_days", None) if r else None,
        "REFERRAL_REWARD_DAYS",
        7,
    )
    thread = getattr(r, "landing_bulletin_message_thread_id", None) if r else None
    thread_id: int | None
    if thread is not None:
        try:
            thread_id = int(thread)
        except (TypeError, ValueError):
            thread_id = None
    else:
        thread_raw = (os.getenv("TBCC_LANDING_BULLETIN_MESSAGE_THREAD_ID") or "").strip()
        thread_id = int(thread_raw) if thread_raw.isdigit() else None

    mode = _str_or_env(
        getattr(r, "referral_mode", None) if r else None,
        "REFERRAL_MODE",
        "premium",
    ).lower().strip() or "premium"

    if r is not None and r.landing_bulletin_intro is not None:
        intro = (r.landing_bulletin_intro or "").strip()
    else:
        intro = (os.getenv("TBCC_LANDING_BULLETIN_INTRO") or "").strip()

    bot_user = _str_or_env(
        getattr(r, "landing_bulletin_bot_username", None) if r else None,
        "TBCC_LANDING_BULLETIN_BOT_USERNAME",
        "",
    )
    if not bot_user:
        bot_user = (os.getenv("BOT_USERNAME") or "YOUR_BOT").strip().lstrip("@")

    return {
        "landing_bulletin_chat_id": _str_or_env(
            getattr(r, "landing_bulletin_chat_id", None) if r else None,
            "TBCC_LANDING_BULLETIN_CHAT_ID",
            "",
        ),
        "landing_bulletin_message_thread_id": thread_id,
        "landing_bulletin_hour_utc": max(0, min(23, hour)),
        "landing_bulletin_bot_username": bot_user.lstrip("@"),
        "landing_bulletin_intro": intro if intro else None,
        "referral_group_invite_link": _str_or_env(
            getattr(r, "referral_group_invite_link", None) if r else None,
            "REFERRAL_GROUP_INVITE_LINK",
            "",
        ),
        "referral_group_name": _str_or_env(
            getattr(r, "referral_group_name", None) if r else None,
            "REFERRAL_GROUP_NAME",
            "our community",
        ),
        "referral_reward_days": reward_days,
        "referral_mode": mode if mode in ("community", "premium") else "premium",
        "milestone_progress_chat_id": _str_or_env(
            getattr(r, "milestone_progress_chat_id", None) if r else None,
            "MILESTONE_PROGRESS_CHAT_ID",
            "",
        ),
    }
