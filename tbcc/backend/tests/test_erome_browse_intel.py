"""Tests for Erome browse-intel ingest + flywheel tag boost."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.content_pool import ContentPool
from app.models.media import Media
from app.services import erome_browse_intel as ebi
from app.services.export_flywheel_service import rank_pool_media


def _patch_intel_paths(monkeypatch, tmp_path):
    ledger = tmp_path / "browse-intel.jsonl"
    drop = tmp_path / "browse-intel-drop.jsonl"
    monkeypatch.setattr(ebi, "ledger_path", lambda: ledger)
    monkeypatch.setattr(ebi, "drop_path", lambda: drop)
    monkeypatch.setattr(ebi, "browse_intel_enabled", lambda: True)
    return ledger, drop


def test_ingest_rows_dedupes_by_album_day(monkeypatch, tmp_path):
    ledger, _ = _patch_intel_paths(monkeypatch, tmp_path)
    row = {
        "captured_at": "2026-07-03T12:00:00Z",
        "album_url": "https://www.erome.com/a/abc123",
        "views": 1000,
        "likes": 50,
        "tags": ["milf", "webcam"],
        "videos": 2,
        "images": 0,
        "format_bucket": "multi_video",
    }
    r1 = ebi.ingest_rows([row])
    assert r1["appended"] == 1
    r2 = ebi.ingest_rows([row])
    assert r2["appended"] == 0
    assert len(ebi._read_jsonl(ledger)) == 1


def test_aggregate_tag_scores_weights_views(monkeypatch, tmp_path):
    _patch_intel_paths(monkeypatch, tmp_path)
    ebi.ingest_rows(
        [
            {
                "captured_at": "2026-07-03T12:00:00Z",
                "album_url": "https://www.erome.com/a/a1",
                "views": 10_000,
                "likes": 500,
                "tags": ["milf"],
            },
            {
                "captured_at": "2026-07-03T13:00:00Z",
                "album_url": "https://www.erome.com/a/a2",
                "views": 100,
                "likes": 2,
                "tags": ["boring"],
            },
        ]
    )
    scores = ebi.aggregate_tag_scores()
    assert scores["milf"] > scores["boring"]


def test_sync_from_drop_file(monkeypatch, tmp_path):
    ledger, drop = _patch_intel_paths(monkeypatch, tmp_path)
    drop.write_text(
        '{"album_url":"https://www.erome.com/a/x","views":500,"tags":["test"]}\n',
        encoding="utf-8",
    )
    result = ebi.sync_from_drop_file()
    assert result["appended"] == 1
    assert not drop.is_file()
    assert len(ebi._read_jsonl(ledger)) == 1


def test_normalize_row_v42_fields(monkeypatch, tmp_path):
    _patch_intel_paths(monkeypatch, tmp_path)
    row = {
        "platform": "erome",
        "captured_at": "2026-07-03T12:00:00Z",
        "album_url": "https://www.erome.com/a/abc123",
        "views": 1000,
        "likes": 50,
        "tags": ["milf"],
        "uploaded_at_approx_days_ago": 2.0,
        "uploader": "someuser",
        "is_uploader_verified": True,
        "media_sequence": ["video", "image"],
    }
    result = ebi.ingest_rows([row])
    assert result["appended"] == 1
    stored = ebi._read_jsonl(ebi.ledger_path())[0]
    assert stored["views_per_day_proxy"] == 500.0
    assert stored["uploader"] == "someuser"
    assert stored["is_uploader_verified"] is True
    assert stored["media_sequence"] == ["video", "image"]


def test_rank_pool_media_boosts_intel_tags(db, monkeypatch, tmp_path):
    _patch_intel_paths(monkeypatch, tmp_path)
    ebi.ingest_rows(
        [
            {
                "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "album_url": "https://www.erome.com/a/hot",
                "views": 50_000,
                "likes": 2000,
                "tags": ["milf"],
            }
        ]
    )
    monkeypatch.setenv("TBCC_EXPORT_FLYWHEEL_RANK_PICKS", "1")
    monkeypatch.setenv("TBCC_EROME_BROWSE_INTEL_RANK", "1")

    pool = ContentPool(id=1, name="Test Pool", album_size=5)
    db.add(pool)
    db.add(
        Media(
            id=1,
            telegram_message_id=1,
            file_id="f1",
            file_unique_id="u1",
            pool_id=1,
            status="approved",
            tags="boring,other",
            created_at=datetime.utcnow(),
        )
    )
    db.add(
        Media(
            id=2,
            telegram_message_id=2,
            file_id="f2",
            file_unique_id="u2",
            pool_id=1,
            status="approved",
            tags="milf,webcam",
            created_at=datetime.utcnow(),
        )
    )
    db.commit()

    ranked = rank_pool_media(db, 1, 2, randomize=False)
    assert [m.id for m in ranked] == [2, 1]
