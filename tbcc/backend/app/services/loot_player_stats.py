"""Per-player loot roll counter (preview + live drops) and free pull allowance."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.loot import LootPlayerStats
from app.services.loot_tier_catalog import FREE_PULL_LIMIT


def _row(db: Session, telegram_user_id: int) -> LootPlayerStats:
    uid = int(telegram_user_id)
    row = db.query(LootPlayerStats).filter(LootPlayerStats.telegram_user_id == uid).first()
    if not row:
        row = LootPlayerStats(
            telegram_user_id=uid,
            roll_count=0,
            free_pulls_used=0,
            first_roll_at=datetime.utcnow(),
        )
        db.add(row)
        db.flush()
    return row


def get_lifetime_roll_index(db: Session, telegram_user_id: int | None) -> int:
    if not telegram_user_id:
        return 0
    row = db.query(LootPlayerStats).filter(LootPlayerStats.telegram_user_id == int(telegram_user_id)).first()
    return int(row.roll_count or 0) if row else 0


def free_pull_allowance(db: Session, telegram_user_id: int) -> int:
    row = db.query(LootPlayerStats).filter(LootPlayerStats.telegram_user_id == int(telegram_user_id)).first()
    bonus = int(row.bonus_free_pulls or 0) if row else 0
    return FREE_PULL_LIMIT + max(0, bonus)


def free_pulls_remaining(db: Session, telegram_user_id: int) -> int:
    row = db.query(LootPlayerStats).filter(LootPlayerStats.telegram_user_id == int(telegram_user_id)).first()
    used = int(row.free_pulls_used or 0) if row else 0
    return max(0, free_pull_allowance(db, int(telegram_user_id)) - used)


def record_roll(db: Session, telegram_user_id: int | None) -> int:
    """Increment paid/preview roll count; returns index *before* this roll (0 = first roll)."""
    if not telegram_user_id:
        return 0
    row = _row(db, int(telegram_user_id))
    idx = int(row.roll_count or 0)
    row.roll_count = idx + 1
    row.last_roll_at = datetime.utcnow()
    db.commit()
    return idx


def record_free_pull(db: Session, telegram_user_id: int) -> int:
    """Increment free_pulls_used; returns count *before* this pull."""
    row = _row(db, int(telegram_user_id))
    used_before = int(row.free_pulls_used or 0)
    row.free_pulls_used = used_before + 1
    row.last_roll_at = datetime.utcnow()
    db.commit()
    return used_before
