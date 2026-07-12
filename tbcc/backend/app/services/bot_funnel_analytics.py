"""Bot funnel rollup for dashboard (growth attribution + loot player stats)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.loot import LootPlayerStats
from app.services.growth_attribution import attribution_summary


def _payment_bot_username() -> str:
    return (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "aofsubscriptions_bot").strip().lstrip("@")


def _loot_bot_username() -> str:
    return (os.getenv("TBCC_LOOT_BOT_USERNAME") or "aof_lootgod_bot").strip().lstrip("@")


def loot_player_stats_summary(db: Session) -> dict[str, Any]:
    rows = db.query(LootPlayerStats).all()
    unique_players = len(rows)
    total_rolls = sum(int(r.roll_count or 0) for r in rows)
    free_pulls_used = sum(int(r.free_pulls_used or 0) for r in rows)
    active_7d = 0
    cutoff = datetime.utcnow() - timedelta(days=7)
    for r in rows:
        if r.last_roll_at and r.last_roll_at >= cutoff:
            active_7d += 1
    return {
        "unique_players": unique_players,
        "total_rolls": total_rolls,
        "free_pulls_used": free_pulls_used,
        "active_players_7d": active_7d,
    }


def bot_funnel_summary(db: Session, *, days: int = 30) -> dict[str, Any]:
    loot_un = _loot_bot_username()
    pay_un = _payment_bot_username()
    return {
        "range_days": days,
        "attribution": attribution_summary(db, days=days),
        "loot_players": loot_player_stats_summary(db),
        "deep_links": {
            "loot_free_pull": f"https://t.me/{loot_un}?start=loot_free",
            "loot_paid_checkout": f"https://t.me/{pay_un}?start=loot",
            "payment_bot_menu_loot": f"https://t.me/{pay_un}?start=menu_loot",
        },
        "bots": {
            "loot_overseer": loot_un,
            "payment": pay_un,
        },
    }
