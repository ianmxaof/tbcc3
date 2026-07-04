"""Per-account modifier dedupe for loot rolls."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.loot import LootPlayerModifierSeen


def seen_modifier_ids(db: Session, telegram_user_id: int) -> set[int]:
    uid = int(telegram_user_id)
    rows = (
        db.query(LootPlayerModifierSeen.modifier_id)
        .filter(LootPlayerModifierSeen.telegram_user_id == uid)
        .all()
    )
    return {int(x[0]) for x in rows if x[0] is not None}


def record_modifiers_seen(db: Session, telegram_user_id: int, modifier_ids: list[int]) -> None:
    uid = int(telegram_user_id)
    now = datetime.utcnow()
    for mid in modifier_ids:
        mid_i = int(mid)
        row = (
            db.query(LootPlayerModifierSeen)
            .filter(
                LootPlayerModifierSeen.telegram_user_id == uid,
                LootPlayerModifierSeen.modifier_id == mid_i,
            )
            .first()
        )
        if row:
            row.last_seen_at = now
            row.seen_count = int(row.seen_count or 0) + 1
        else:
            db.add(
                LootPlayerModifierSeen(
                    telegram_user_id=uid,
                    modifier_id=mid_i,
                    last_seen_at=now,
                    seen_count=1,
                )
            )
    db.commit()
