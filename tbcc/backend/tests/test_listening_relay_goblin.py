"""Loot goblin roll, claim cap, and compose integration tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.goblin_claim import GoblinClaim
from app.models.goblin_drop import GoblinDrop
from app.models.listening_relay_settings import ListeningRelaySettings
from app.services.goblin_roll import note_scrobble_for_goblin
from app.services.goblin_service import claim_goblin_drop, create_goblin_drop, revoke_goblin_drop
from app.services.listening_relay_compose import build_relay_outbound


def _relay_row(**kwargs) -> ListeningRelaySettings:
    row = ListeningRelaySettings(id=1, enabled=True)
    row.goblin_mode_enabled = True
    row.goblin_spawn_chance = 1.0
    row.goblin_cooldown_minutes = 0
    row.goblin_max_per_day_utc = 5
    row.goblin_spawns_today = 0
    row.goblin_utc_day = None
    row.message_template_html = "<b>{artist}</b> — {title}"
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


def test_goblin_roll_disabled(db):
    row = _relay_row(goblin_mode_enabled=False)
    assert note_scrobble_for_goblin(row, db) is False


def test_goblin_roll_daily_cap(db):
    row = _relay_row(goblin_spawns_today=5, goblin_utc_day=datetime.utcnow().strftime("%Y-%m-%d"))
    assert note_scrobble_for_goblin(row, db) is False


def test_goblin_roll_cooldown(db):
    row = _relay_row(goblin_last_spawn_at=datetime.utcnow() - timedelta(minutes=5), goblin_cooldown_minutes=120)
    assert note_scrobble_for_goblin(row, db) is False


@patch("app.services.goblin_roll.random.random", return_value=0.0)
@patch("app.services.goblin_roll.relay_may_send_now", return_value=True)
def test_goblin_roll_success_increments_counter(_admit, _rng, db):
    row = _relay_row()
    now = datetime.utcnow()
    assert note_scrobble_for_goblin(row, db, now=now) is True
    assert int(row.goblin_spawns_today) == 1
    assert row.goblin_last_spawn_at == now


@patch("app.services.goblin_roll.random.random", return_value=0.99)
@patch("app.services.goblin_roll.relay_may_send_now", return_value=True)
def test_goblin_roll_chance_miss(_admit, _rng, db):
    row = _relay_row(goblin_spawn_chance=0.1)
    assert note_scrobble_for_goblin(row, db) is False


@patch("app.services.goblin_roll.relay_may_send_now", return_value=True)
@patch("app.services.goblin_roll.random.random", return_value=0.0)
def test_compose_sets_goblin_spawn_flag(_rng, _admit, db):
    row = _relay_row()
    outbound = build_relay_outbound(
        row,
        artist="Artist",
        title="Track",
        album=None,
        url=None,
        source="lastfm",
        source_label="Last.fm",
        consume=True,
        db=db,
    )
    assert outbound.goblin_spawn is True


def test_claim_atomic_cap(db):
    drop = create_goblin_drop(db, channel_id=1, message_thread_id=None, relay_log_id=None)
    drop.claims_cap = 2
    db.commit()

    with patch("app.services.goblin_service._deliver_goblin_pull", return_value={"ok": True, "delivery": {"media_sent": 1}}):
        r1 = claim_goblin_drop(db, token=drop.token, telegram_user_id=101)
        r2 = claim_goblin_drop(db, token=drop.token, telegram_user_id=102)
        r3 = claim_goblin_drop(db, token=drop.token, telegram_user_id=103)

    assert r1["ok"] is True
    assert r2["ok"] is True
    assert r3.get("ok") is False
    assert r3.get("reason") == "exhausted"

    refreshed = db.query(GoblinDrop).filter(GoblinDrop.id == drop.id).first()
    assert int(refreshed.claims_used) == 2
    assert refreshed.status == "exhausted"
    assert db.query(GoblinClaim).count() == 2


def test_double_claim_rejected(db):
    drop = create_goblin_drop(db, channel_id=1, message_thread_id=None, relay_log_id=None)
    db.commit()
    with patch("app.services.goblin_service._deliver_goblin_pull", return_value={"ok": True, "delivery": {"media_sent": 1}}):
        first = claim_goblin_drop(db, token=drop.token, telegram_user_id=555)
        second = claim_goblin_drop(db, token=drop.token, telegram_user_id=555)
    assert first["ok"] is True
    assert second.get("ok") is False
    assert second.get("reason") == "already_claimed"


def test_revoke_kills_claim(db):
    drop = create_goblin_drop(db, channel_id=1, message_thread_id=None, relay_log_id=None)
    db.commit()
    with patch("app.services.goblin_announce.delete_goblin_announce", return_value={"ok": True}):
        out = revoke_goblin_drop(db, token=drop.token)
    assert out["ok"] is True
    with patch("app.services.goblin_service._deliver_goblin_pull", return_value={"ok": True, "delivery": {"media_sent": 1}}):
        claim = claim_goblin_drop(db, token=drop.token, telegram_user_id=9)
    assert claim.get("ok") is False
    assert claim.get("reason") == "revoked"
