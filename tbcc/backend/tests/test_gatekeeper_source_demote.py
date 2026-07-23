"""Tests for gatekeeper source demote streak."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.data.media_gatekeeper_spec import SOURCE_DEMOTE_REJECT_STREAK
from app.services.gatekeeper_source_demote import (
    demote_scrape_source,
    demote_streak_threshold,
    increment_reject_streak,
    is_source_banned,
    record_operator_reject,
    reset_reject_streak,
)


def test_demote_streak_threshold_default():
    assert demote_streak_threshold() == SOURCE_DEMOTE_REJECT_STREAK


def test_increment_and_reset_streak(monkeypatch):
    monkeypatch.setattr(
        "app.services.gatekeeper_source_demote._redis",
        lambda: (_ for _ in ()).throw(ConnectionError("test")),
    )
    cid = -1009990001
    reset_reject_streak(cid)
    assert increment_reject_streak(cid) == 1
    assert increment_reject_streak(cid) == 2
    reset_reject_streak(cid)
    assert increment_reject_streak(cid) == 1


def test_record_operator_reject_demotes_at_threshold(monkeypatch):
    monkeypatch.setenv("TBCC_GATEKEEPER_DEMOTE_STREAK", "3")
    monkeypatch.setattr(
        "app.services.gatekeeper_source_demote._redis",
        lambda: (_ for _ in ()).throw(ConnectionError("test")),
    )
    cid = -1009990002
    reset_reject_streak(cid)

    media = MagicMock()
    media.source_channel = str(cid)

    src = MagicMock()
    src.active = True
    src.identifier = str(cid)
    src.source_type = "telegram_channel"

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [src]

    out1 = record_operator_reject(db, media)
    assert out1["demoted"] is False
    out2 = record_operator_reject(db, media)
    assert out2["demoted"] is False
    out3 = record_operator_reject(db, media)
    assert out3["demoted"] is True
    assert is_source_banned(cid) is True
    demote_scrape_source(db, cid)
    assert src.active is False
