"""Loot roll candidate filter includes local-disk pool media."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.services.loot_roll_preview import _pools_for_tier


class _Elig:
    def __init__(self, pid: int):
        self.content_pool_id = pid
        self.loot_enabled = True
        self.min_rarity_tier = 1
        self.max_rarity_tier = 10
        self.base_weight = 1.0


def test_loot_candidate_query_local_only_by_default(monkeypatch):
    """Default policy: only local-disk approved rows are roll candidates."""
    monkeypatch.setenv("TBCC_LOOT_LOCAL_BYTES_ONLY", "1")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models.base import Base
    from app.models.media import Media
    from app.services.loot_media_deliverable import filter_roll_candidates

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    local = Media(
        telegram_message_id=0,
        file_id="local:abc123.jpg",
        file_unique_id="local:deadbeef",
        media_type="photo",
        pool_id=1,
        status="approved",
    )
    saved = Media(
        telegram_message_id=999,
        file_id="tg-file",
        file_unique_id="uniq-saved",
        media_type="photo",
        pool_id=1,
        status="approved",
    )
    db.add_all([local, saved])
    db.commit()

    rows = db.query(Media).filter(Media.status == "approved", Media.pool_id.in_([1])).all()
    with patch("app.services.loot_media_deliverable.loot_media_has_local_bytes", side_effect=lambda m: m.file_id.startswith("local:")):
        ids = {int(r.id) for r in filter_roll_candidates(rows)}
    assert local.id in ids
    assert saved.id not in ids
    db.close()


def test_loot_candidate_query_allows_local_and_saved(monkeypatch):
    """Legacy mode: approved local rows and Saved Messages refs."""
    monkeypatch.setenv("TBCC_LOOT_LOCAL_BYTES_ONLY", "0")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models.base import Base
    from app.models.media import Media

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    local = Media(
        telegram_message_id=0,
        file_id="local:abc123.jpg",
        file_unique_id="local:deadbeef",
        media_type="photo",
        pool_id=1,
        status="approved",
    )
    saved = Media(
        telegram_message_id=999,
        file_id="tg-file",
        file_unique_id="uniq-saved",
        media_type="photo",
        pool_id=1,
        status="approved",
    )
    rejected = Media(
        telegram_message_id=888,
        file_id="tg-file-2",
        file_unique_id="uniq-dead",
        media_type="photo",
        pool_id=1,
        status="rejected",
    )
    db.add_all([local, saved, rejected])
    db.commit()

    # Mirror the filter used in build_loot_roll_preview without running full roll.
    from sqlalchemy import and_, or_

    rows = (
        db.query(Media)
        .filter(
            Media.status == "approved",
            Media.pool_id.in_([1]),
            or_(
                and_(Media.telegram_message_id == 0, Media.file_id.like("local:%")),
                Media.telegram_message_id > 0,
            ),
        )
        .all()
    )
    ids = {int(r.id) for r in rows}
    assert local.id in ids
    assert saved.id in ids
    assert rejected.id not in ids
    db.close()


def test_pools_for_tier_still_returns_enabled_rows():
    rows = [_Elig(1), _Elig(2)]
    got = _pools_for_tier(rows, rarity=3)  # type: ignore[arg-type]
    assert [r.content_pool_id for r in got] == [1, 2]
