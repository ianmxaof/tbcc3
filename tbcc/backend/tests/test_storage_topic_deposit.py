"""Tests for Storage Hub /deposit command parsing and replies."""

from types import SimpleNamespace

from app.services.storage_topic_deposit import (
    deposit_mirror_countdown_s,
    format_deposit_complete_text,
    format_deposit_progress_text,
    parse_deposit_command,
    resolve_deposit_limit,
)
from app.services.telegram_storage import batch_messages_for_album_mirror


def test_parse_deposit_with_limit():
    assert parse_deposit_command("/deposit 15") == (15, None)
    assert parse_deposit_command("/deposit 15 videos") == (15, "videos")
    assert parse_deposit_command("/deposit  20  both") == (20, "both")


def test_parse_deposit_default_limit():
    assert parse_deposit_command("/deposit") == (None, None)
    assert parse_deposit_command("/deposit@SomeBot 12") == (12, None)


def test_parse_deposit_not_command():
    assert parse_deposit_command("/status") is None
    assert parse_deposit_command("hello") is None


def test_resolve_deposit_limit_caps():
    assert resolve_deposit_limit(500) == 200
    assert resolve_deposit_limit(0) == 1


def test_format_deposit_progress_mentions_job():
    report = {"pool_name": "POOL", "topic_title": "TOPIC", "limit": 10, "media_types": "videos", "job_id": "abc"}
    text = format_deposit_progress_text(report, html=False).lower()
    assert "uploading media" in text
    assert "abc" in text


def test_format_deposit_progress_plain_no_markup():
    report = {"pool_name": "POOL", "topic_title": "TOPIC", "limit": 10, "media_types": "videos", "job_id": "abc"}
    text = format_deposit_progress_text(report, html=False, markdown=False)
    assert "<b>" not in text
    assert "**" not in text
    assert "Topic: TOPIC" in text


def test_deposit_mirror_countdown_scales_with_limit():
    assert deposit_mirror_countdown_s(30) == 240  # min(30*8, 300)
    assert deposit_mirror_countdown_s(1) == 120  # floor 120s


def test_format_deposit_complete_all_duplicates():
    report = {
        "pool_name": "AOF TABOO POOL",
        "topic_title": "AOF TABOO 18+ STORAGE",
        "limit": 30,
        "media_types": "both",
        "job_id": "abc",
    }
    job_body = {
        "status": "done",
        "result": {
            "stored": 0,
            "skipped_duplicate": 122,
            "target_stored": 30,
            "messages_scanned": 133,
        },
    }
    text = format_deposit_complete_text(report, job_body, html=False)
    assert "already in this pool" in text
    assert "Upload newer content" in text


def test_batch_messages_for_album_mirror_groups_consecutive_photos():
    msgs = [
        SimpleNamespace(id=10, grouped_id=None, media=object()),
        SimpleNamespace(id=11, grouped_id=None, media=object()),
        SimpleNamespace(id=12, grouped_id=None, media=object()),
    ]
    batches = batch_messages_for_album_mirror(msgs, bucket_fn=lambda _m: "photo")
    assert batches == [msgs]


def test_batch_messages_for_album_mirror_full_album_chunks():
    msgs = [SimpleNamespace(id=i, grouped_id=None, media=object()) for i in range(1, 26)]
    batches = batch_messages_for_album_mirror(msgs, bucket_fn=lambda _m: "photo", require_full_albums=True)
    assert [len(b) for b in batches] == [10, 10, 5]


def test_batch_messages_for_album_mirror_splits_mixed_buckets():
    msgs = [
        SimpleNamespace(id=1, grouped_id=None, media=object()),
        SimpleNamespace(id=2, grouped_id=None, media=object()),
        SimpleNamespace(id=3, grouped_id=None, media=object()),
    ]
    batches = batch_messages_for_album_mirror(
        msgs,
        bucket_fn=lambda m: "photo" if m.id != 3 else "video",
    )
    assert batches == [msgs[:2], [msgs[2]]]