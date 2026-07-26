"""Tests for storage deposit auto-approve and enrich kill switch."""

from unittest.mock import MagicMock

from app.services.auto_tag_enrich import enrich_pipeline_enabled
from app.services.storage_deposit_auto_approve import (
    clip_tags_passed,
    is_storage_hub_source_label,
    maybe_auto_approve_storage_deposit_media,
)


def test_storage_hub_source_label():
    assert is_storage_hub_source_label("telegram:-1003812457581#topic:11281")
    assert not is_storage_hub_source_label("telegram:-1003997525573")


def test_clip_tags_passed():
    assert clip_tags_passed({"clip_tags": 2})
    assert clip_tags_passed({"clip": True, "clip_confident": True})
    assert not clip_tags_passed({"clip": True})


def test_auto_approve_immediate_without_clip(monkeypatch):
    monkeypatch.setenv("TBCC_STORAGE_DEPOSIT_AUTO_APPROVE", "1")
    monkeypatch.setenv("TBCC_STORAGE_DEPOSIT_AUTO_APPROVE_REQUIRES_CLIP", "0")
    monkeypatch.setenv("TBCC_MEDIA_GATEKEEPER_ENABLED", "0")
    media = MagicMock()
    media.id = 9
    media.status = "pending"
    media.source_channel = "telegram:-1003812457581#topic:11281"
    media.pool_id = 8
    pool = MagicMock()
    pool.id = 8
    pool.name = "AOF ASS POOL"

    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [media, media, pool]

    out = maybe_auto_approve_storage_deposit_media(db, 9, {})
    assert out["applied"] is True
    assert out["mode"] == "immediate"
    assert media.status == "approved"
    db.commit.assert_called()


def test_auto_approve_requires_clip_when_configured(monkeypatch):
    monkeypatch.setenv("TBCC_STORAGE_DEPOSIT_AUTO_APPROVE", "1")
    monkeypatch.setenv("TBCC_STORAGE_DEPOSIT_AUTO_APPROVE_REQUIRES_CLIP", "1")
    monkeypatch.setenv("TBCC_MEDIA_GATEKEEPER_ENABLED", "0")
    media = MagicMock()
    media.id = 9
    media.status = "pending"
    media.source_channel = "telegram:-1003812457581#topic:11281"
    media.pool_id = 25
    pool = MagicMock()
    pool.id = 25
    pool.name = "AOF FULL LENGTH POOL"

    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [
        media,  # call1 m_pre
        media,  # call2 m_pre
        media,  # call2 m
        pool,   # call2 pool
    ]

    out = maybe_auto_approve_storage_deposit_media(db, 9, {})
    assert out["applied"] is False
    assert out["reason"] == "clip_tags_missing"

    out2 = maybe_auto_approve_storage_deposit_media(db, 9, {"clip_tags": 3})
    assert out2["applied"] is True
    assert out2["mode"] == "clip"


def test_scrape_origin_blocked_even_when_gatekeeper_disabled(monkeypatch):
    monkeypatch.setenv("TBCC_STORAGE_DEPOSIT_AUTO_APPROVE", "1")
    monkeypatch.setenv("TBCC_MEDIA_GATEKEEPER_ENABLED", "0")
    media = MagicMock()
    media.id = 99
    media.status = "pending"
    media.source_channel = "-1003271959583"
    media.pool_id = 8
    src = MagicMock()
    src.name = "SCRP [ASS SCRP]: test"
    src.source_type = "telegram_channel"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [media, src]
    out = maybe_auto_approve_storage_deposit_media(db, 99, source_label="-1003271959583")
    assert out["applied"] is False
    assert out["reason"] == "scrape_origin_blocked"


def test_enrich_kill_switch(monkeypatch):
    monkeypatch.setenv("TBCC_ENRICH_ON_IMPORT", "0")
    monkeypatch.setenv("TBCC_CLIP_CATEGORIZE_URL", "http://127.0.0.1:8002")
    monkeypatch.setenv("TBCC_NSFW_DETECT_URL", "http://127.0.0.1:8001")
    assert enrich_pipeline_enabled() is False

    monkeypatch.delenv("TBCC_ENRICH_ON_IMPORT", raising=False)
    monkeypatch.delenv("TBCC_CLIP_CATEGORIZE_URL", raising=False)
    monkeypatch.delenv("TBCC_NSFW_DETECT_URL", raising=False)
    monkeypatch.setenv("TBCC_AUTO_TAG_ON_IMPORT", "1")
    assert enrich_pipeline_enabled() is False

    monkeypatch.setenv("TBCC_CLIP_CATEGORIZE_URL", "http://127.0.0.1:8002")
    assert enrich_pipeline_enabled() is True


def test_enrich_backlog_skips_when_disabled(monkeypatch):
    monkeypatch.setenv("TBCC_ENRICH_ON_IMPORT", "0")
    from app.services.auto_tag_enrich import run_auto_tag_enrich_for_media

    out = run_auto_tag_enrich_for_media(1)
    assert out.get("skipped") == "enrich_disabled"
