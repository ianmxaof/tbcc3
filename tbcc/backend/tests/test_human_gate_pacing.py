"""Human gate pacing — robot ack opt-in + DM outreach pool."""

from datetime import datetime, timedelta, timezone

from app.database.session import SessionLocal, engine
from app.models.base import Base
from app.models.funnel_dm_consent import FunnelDmConsent
from app.models.funnel_strategy import FunnelStrategyEntry
from app.services.funnel_rag import seed_human_gate_funnel_strategies
from app.services.human_gate_pacing import (
    collect_human_gate_dm_user_ids,
    parse_gate_start_payload,
    record_human_ack,
    resolve_gate_invite_url,
)


def test_parse_gate_start_payload():
    assert parse_gate_start_payload("gate_loot") == "loot_room"
    assert parse_gate_start_payload("gate") == "loot_room"
    assert parse_gate_start_payload("gate_vip") == "vip"
    assert parse_gate_start_payload("bait_loot") is None


def test_record_and_collect_dm_pool(monkeypatch):
    monkeypatch.setenv("TBCC_HUMAN_GATE_DM_DELAY_DAYS", "0")
    Base.metadata.create_all(
        engine, tables=[FunnelDmConsent.__table__, FunnelStrategyEntry.__table__]
    )
    db = SessionLocal()
    try:
        record_human_ack(db, telegram_user_id=424242, gate_target="loot_room", source="gate")
        ids = collect_human_gate_dm_user_ids(db)
        assert 424242 in ids
    finally:
        db.close()


def test_seed_human_gate_rag_idempotent():
    Base.metadata.create_all(engine, tables=[FunnelStrategyEntry.__table__])
    db = SessionLocal()
    try:
        n1 = seed_human_gate_funnel_strategies(db)
        n2 = seed_human_gate_funnel_strategies(db)
        assert n1 >= 0
        assert n2 == 0
        assert db.query(FunnelStrategyEntry).filter(FunnelStrategyEntry.pattern == "human_gate_opt_in").count() >= 1
    finally:
        db.close()


def test_resolve_gate_invite_urls():
    url, label = resolve_gate_invite_url("loot_room")
    assert "t.me" in url
    assert "Loot" in label
