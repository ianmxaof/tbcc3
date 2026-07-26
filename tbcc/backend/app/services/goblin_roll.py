"""Rarity roll for loot goblin spawns on listening relay scrobbles."""

from __future__ import annotations

import random
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.listening_relay_settings import ListeningRelaySettings
from app.services.listening_relay_admission import relay_may_send_now


def _utc_day(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def note_scrobble_for_goblin(row: ListeningRelaySettings, db: Session, *, now: datetime | None = None) -> bool:
    """
  Return True when this scrobble should spawn a goblin announce (settings + caps + roll).
  Mutates row counters when a spawn is accepted.
  """
    if not bool(getattr(row, "goblin_mode_enabled", False)):
        return False
    if not relay_may_send_now(db):
        return False

    now = now or datetime.utcnow()
    day = _utc_day(now)
    max_day = max(1, int(getattr(row, "goblin_max_per_day_utc", None) or 3))
    if getattr(row, "goblin_utc_day", None) != day:
        row.goblin_utc_day = day
        row.goblin_spawns_today = 0
    if int(getattr(row, "goblin_spawns_today", None) or 0) >= max_day:
        return False

    cooldown_m = max(0, int(getattr(row, "goblin_cooldown_minutes", None) or 120))
    last = getattr(row, "goblin_last_spawn_at", None)
    if last and cooldown_m > 0:
        if (now - last).total_seconds() < cooldown_m * 60:
            return False

    chance = float(getattr(row, "goblin_spawn_chance", None) or 0.2)
    chance = max(0.0, min(1.0, chance))
    if random.random() > chance:
        return False

    row.goblin_last_spawn_at = now
    row.goblin_spawns_today = int(getattr(row, "goblin_spawns_today", None) or 0) + 1
    return True
