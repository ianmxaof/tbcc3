"""Stress / concurrency readiness for aof_lootgod_bot game loop.

Does not talk to Telegram. Safe to run offline; documents race windows for iteration.
"""

from __future__ import annotations

import random
import threading
from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.loot import LootPlayerStats
from app.services.loot_player_stats import (
    free_pulls_remaining,
    record_free_pull,
    record_roll,
)
from app.services.loot_roll_presentation import build_album_caption_html, pick_tier_flavor
from app.services.loot_tier_catalog import (
    FREE_PULL_LIMIT,
    FREE_PULL_MAX_TIER,
    roll_free_rarity_tier,
    tier_display_name,
)
from app.services.loot_vip_daily_pull import vip_daily_pull_used_today


def _memory_sessions():
    """Shared in-memory SQLite for light concurrent sessions."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session


def test_free_rarity_distribution_stress():
    """10k free rolls stay in 1..5 and roughly follow weights."""
    rng = random.Random(7)
    counts = {i: 0 for i in range(1, 6)}
    for _ in range(10_000):
        t = roll_free_rarity_tier(rng)
        assert 1 <= t <= FREE_PULL_MAX_TIER
        counts[t] += 1
    # Soft shape check: mid tiers not empty; godroll free path impossible
    assert counts[1] > 1500
    assert counts[5] > 1000
    assert sum(counts.values()) == 10_000


def test_caption_builder_stress_no_throw():
    """Hundreds of caption builds (all tiers × album sizes) stay under Telegram-ish length."""
    for tier in range(1, 11):
        for items in (1, 3, 8, 10):
            for mods in (0, 1, 3):
                preview = {
                    "rarity_tier": tier,
                    "modifier_slot_count": mods,
                    "tier_flavor": pick_tier_flavor(tier, random.Random(tier * 17 + items)),
                }
                lines = [f"• mod {i} — <a href=\"https://ex.test/{i}\">open</a>" for i in range(mods)]
                html = build_album_caption_html(
                    preview,
                    modifier_lines=lines or None,
                    item_count=items,
                    affiliate_footer_html='<i>tip — <a href="https://aff.test">x</a></i>',
                )
                assert tier_display_name(tier).split("·")[0].strip() in html or f"Tier {tier}" in html
                assert len(html) < 4000  # Bot API caption soft ceiling for HTML albums


def test_sequential_free_pull_budget_hard_cap(db):
    uid = 424242
    for i in range(FREE_PULL_LIMIT):
        assert free_pulls_remaining(db, uid) == FREE_PULL_LIMIT - i
        record_free_pull(db, uid)
    assert free_pulls_remaining(db, uid) == 0
    # Extra record still increments used (gate must live at claim layer)
    record_free_pull(db, uid)
    row = db.query(LootPlayerStats).filter(LootPlayerStats.telegram_user_id == uid).first()
    assert int(row.free_pulls_used) == FREE_PULL_LIMIT + 1
    assert free_pulls_remaining(db, uid) == 0


def test_concurrent_check_then_act_overshoots_budget_logic():
    """
    Pure race model of claim_free_pull: many workers read remaining, then all commit.

    Documents why POST /loot/free-pull/claim needs atomic UPDATE … WHERE used < limit
    (or SELECT FOR UPDATE) before delivery — SQLite can't demo Postgres races cleanly.
    """
    used = 0
    limit = FREE_PULL_LIMIT
    # All 12 workers sample remaining before any write lands
    snapshots = [limit - used for _ in range(12)]
    for rem in snapshots:
        if rem > 0:
            used += 1
    assert used == 12
    assert used > limit


def test_concurrent_record_roll_monotonic(db):
    """Paid roll counter stays consistent under sequential stress (baseline)."""
    uid = 616161
    for _ in range(200):
        record_roll(db, uid)
    row = db.query(LootPlayerStats).filter(LootPlayerStats.telegram_user_id == uid).first()
    assert int(row.roll_count) == 200


def test_vip_daily_gate_idempotent_read():
    """Used-today gate is pure read — double /viproll must be blocked by claim writer."""
    row = MagicMock()
    from datetime import datetime

    row.vip_daily_pull_at = datetime.utcnow()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row
    assert vip_daily_pull_used_today(db, 99) is True
    assert vip_daily_pull_used_today(db, 99) is True


def test_check_then_act_free_pull_race_documented():
    """API-shaped race: two threads both see remaining=1 and both would claim."""
    engine, Session = _memory_sessions()
    uid = 717171
    with Session() as s:
        row = LootPlayerStats(
            telegram_user_id=uid,
            roll_count=0,
            free_pulls_used=FREE_PULL_LIMIT - 1,  # one left
        )
        s.add(row)
        s.commit()

    saw_ok = []
    barrier = threading.Barrier(2)
    write_gate = threading.Lock()

    def mimic_claim():
        db = Session()
        try:
            barrier.wait(timeout=5)
            rem = free_pulls_remaining(db, uid)
            if rem <= 0:
                saw_ok.append(False)
                return
            # Serialize SQLite writes; race is in the check, not the storage engine.
            with write_gate:
                record_free_pull(db, uid)
            saw_ok.append(True)
        finally:
            db.close()

    t1 = threading.Thread(target=mimic_claim)
    t2 = threading.Thread(target=mimic_claim)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    with Session() as s:
        used = int(
            s.query(LootPlayerStats)
            .filter(LootPlayerStats.telegram_user_id == uid)
            .first()
            .free_pulls_used
        )
    # Ideal: only one True. Reality without lock: often two Trues and used=6.
    assert sum(1 for x in saw_ok if x) >= 1
    assert used >= FREE_PULL_LIMIT
    engine.dispose()
