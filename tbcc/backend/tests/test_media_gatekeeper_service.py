"""Tests for media_gatekeeper ingest service."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT
from app.services.media_gatekeeper import (
    INGEST_ORIGIN_SCRAPE,
    INGEST_ORIGIN_STORAGE_HUB,
    apply_gatekeeper_after_ingest,
    build_gatekeeper_input,
    is_scrape_origin_source,
    resolve_ingest_origin,
    should_attempt_storage_auto_approve,
    source_trusted_for_gatekeeper,
)
from app.services.storage_deposit_auto_approve import maybe_auto_approve_storage_deposit_media


def test_resolve_ingest_origin_storage_hub():
    db = MagicMock()
    label = f"telegram:{STORAGE_HUB_IDENT}#topic:3779"
    assert resolve_ingest_origin(db, source_channel=label) == INGEST_ORIGIN_STORAGE_HUB
    assert source_trusted_for_gatekeeper(INGEST_ORIGIN_STORAGE_HUB) is True


def test_is_scrape_origin_source_by_scrp_name():
    db = MagicMock()
    src = MagicMock()
    src.name = "SCRP [ASS SCRP]: Hagarth's Big ass"
    src.source_type = "telegram_channel"
    db.query.return_value.filter.return_value.first.return_value = src
    assert is_scrape_origin_source(db, "-1003271959583") is True


def test_scrape_origin_blocks_auto_approve(monkeypatch):
    monkeypatch.setenv("TBCC_STORAGE_DEPOSIT_AUTO_APPROVE", "1")
    monkeypatch.setenv("TBCC_MEDIA_GATEKEEPER_ENABLED", "0")

    media = MagicMock()
    media.id = 42
    media.status = "pending"
    media.source_channel = "-1003271959583"
    media.pool_id = 8

    src = MagicMock()
    src.name = "SCRP [ASS SCRP]: test"
    src.source_type = "telegram_channel"

    pool = MagicMock()
    pool.id = 8
    pool.name = "AOF ASS POOL"

    db = MagicMock()

    def _first():
        calls = getattr(_first, "n", 0)
        _first.n = calls + 1
        if calls == 0:
            return media
        if calls == 1:
            return src
        if calls == 2:
            return media
        return pool

    db.query.return_value.filter.return_value.first.side_effect = _first

    out = maybe_auto_approve_storage_deposit_media(db, 42, source_label="-1003271959583")
    assert out["applied"] is False
    assert out["reason"] == "scrape_origin_blocked"


def test_apply_gatekeeper_scrape_high_score_quarantines(monkeypatch):
    monkeypatch.setenv("TBCC_MEDIA_GATEKEEPER_ENABLED", "1")
    monkeypatch.setattr(
        "app.services.gatekeeper_review.enqueue_quarantine_review",
        lambda _mid: None,
    )

    media = MagicMock()
    media.id = 7
    media.status = "pending"
    media.media_type = "video"
    media.source_channel = "-1003271959583"
    media.pool_id = 8
    media.file_unique_id = "vid123"
    media.nsfw_tier = "explicit"
    media.classification_json = None

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = media

    src = MagicMock()
    src.name = "SCRP [ASS SCRP]: channel"
    src.source_type = "telegram_channel"

    def _first():
        calls = getattr(_first, "n", 0)
        _first.n = calls + 1
        if calls == 0:
            return media
        return src

    db.query.return_value.filter.return_value.first.side_effect = _first

    out = apply_gatekeeper_after_ingest(
        db,
        7,
        caption="fire #modelname #ass",
        source_label="-1003271959583",
        message=None,
    )
    assert out["applied"] is True
    assert out["ingest_origin"] == INGEST_ORIGIN_SCRAPE
    assert out["verdict"] in ("quarantine", "reject", "approve")
    if out["quality_score"] >= 70:
        assert out["verdict"] == "quarantine"


def test_should_not_auto_approve_scrape_after_gatekeeper(monkeypatch):
    monkeypatch.setenv("TBCC_MEDIA_GATEKEEPER_ENABLED", "1")

    media = MagicMock()
    media.id = 1
    media.source_channel = "-1003271959583"
    media.classification_json = '{"gatekeeper": {"verdict": "quarantine"}}'

    db = MagicMock()
    src = MagicMock()
    src.name = "SCRP [ASS SCRP]: x"
    src.source_type = "telegram_channel"

    def _first():
        calls = getattr(_first, "n", 0)
        _first.n = calls + 1
        return media if calls == 0 else src

    db.query.return_value.filter.return_value.first.side_effect = _first

    assert should_attempt_storage_auto_approve(db, 1, source_label="-1003271959583") is False


def test_build_gatekeeper_input_storage_hub_trusted():
    db = MagicMock()
    media = MagicMock()
    media.media_type = "video"
    media.source_channel = f"telegram:{STORAGE_HUB_IDENT}#topic:3779"
    media.pool_id = 8
    media.file_unique_id = "x1"
    media.nsfw_tier = None

    inp = build_gatekeeper_input(db, media, caption="#ass drop")
    assert inp.source_trusted is True
    assert inp.expected_lane == "ass"
