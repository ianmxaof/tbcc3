"""Lane Drop Checkpoint service."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.lane_drop import LaneDrop
from app.services.lane_drop_checkpoint import (
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    approve_lane_drop,
    create_lane_drop,
    list_lane_drops,
    reject_lane_drop,
)


def test_create_approve_reject_flow() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[LaneDrop.__table__])
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        row = create_lane_drop(
            db,
            network_key="milf",
            title="MILF glimpse set",
            promo_path="/out/promo_heavy",
            glimpse_paths=["a.jpg", "b.jpg", "c.jpg"],
        )
        assert row.status == STATUS_PENDING
        assert list_lane_drops(db, status=STATUS_PENDING)
        approved = approve_lane_drop(db, row.id, review_note="looks good")
        assert approved.status == STATUS_APPROVED
        row2 = create_lane_drop(db, network_key="ass", title="no")
        rejected = reject_lane_drop(db, row2.id, review_note="thin")
        assert rejected.status == STATUS_REJECTED
    finally:
        db.close()
