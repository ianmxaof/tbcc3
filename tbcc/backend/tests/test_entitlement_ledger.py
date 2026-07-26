"""Entitlement ledger unit tests (in-memory SQLite)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.buyer_entitlement import BuyerEntitlement
from app.services.entitlement_ledger import (
    grant_entitlement,
    list_active_entitlements,
    mark_expired,
    reissue_invites_for_lane,
)


def _session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[BuyerEntitlement.__table__])
    return sessionmaker(bind=eng)()


def test_grant_and_list_lane_pass() -> None:
    db = _session()
    grant_entitlement(
        db,
        telegram_user_id=111,
        kind="lane_pass",
        network_key="milf",
        duration_hours=24,
        invite_url="https://t.me/+test",
    )
    db.commit()
    active = list_active_entitlements(db, telegram_user_id=111, kind="lane_pass")
    assert len(active) == 1
    assert active[0].network_key == "milf"


def test_expire_and_reissue() -> None:
    db = _session()
    row = grant_entitlement(
        db,
        telegram_user_id=222,
        kind="lane_pass",
        network_key="big_tits",
        duration_hours=1,
    )
    row.ends_at = datetime.utcnow() - timedelta(minutes=5)
    db.commit()
    assert mark_expired(db) == 1
    db.commit()
    assert list_active_entitlements(db, network_key="big_tits") == []

    grant_entitlement(
        db,
        telegram_user_id=333,
        kind="lane_pass",
        network_key="big_tits",
        duration_hours=24,
    )
    db.commit()
    out = reissue_invites_for_lane(
        db,
        network_key="big_tits",
        new_invite_url="https://t.me/+backup",
        backup_channel_ident="-100999",
    )
    db.commit()
    assert out["reissued"] == 1
    assert out["telegram_user_ids"] == [333]
    assert out["dm_pending"] is True
