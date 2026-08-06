"""Topic rebundle — loose singles → albums (full + partial leftovers)."""

from types import SimpleNamespace
from unittest.mock import patch

from app.services.topic_rebundle_service import (
    classify_loose_media_messages,
    format_topic_rebundle_summary,
    plan_topic_rebundle_batches,
    topic_rebundle_album_size,
)


def _msg(mid: int, gid=None, *, bucket: str = "photo"):
    return SimpleNamespace(id=mid, grouped_id=gid, media=object(), _bucket=bucket)


def test_classify_loose_media_messages():
    with patch(
        "app.services.topic_rebundle_service._channel_message_media_kind",
        side_effect=lambda m: "photo",
    ):
        loose_msgs = [_msg(1), _msg(2), _msg(3)]
        album_msgs = [_msg(10, 99), _msg(11, 99)]
        all_msgs = loose_msgs + album_msgs
        loose, existing = classify_loose_media_messages(all_msgs)
        assert len(loose) == 3
        assert len(existing) == 2


def test_plan_topic_rebundle_includes_partial_by_default():
    loose = [_msg(i) for i in range(1, 26)]
    with patch(
        "app.services.topic_rebundle_service._message_mirror_bucket",
        side_effect=lambda m: getattr(m, "_bucket", "photo"),
    ):
        plan = plan_topic_rebundle_batches(loose, album_size=10, allow_partial=True)
    assert plan["full_albums"] == 2
    assert plan["partial_albums"] == 1
    assert plan["leftover_singles"] == 0
    assert plan["items_in_albums"] == 25
    assert plan["album_size"] == 10
    sizes = sorted(len(b) for b in plan["batches"])
    assert sizes == [5, 10, 10]


def test_plan_topic_rebundle_full_albums_only_when_disabled():
    loose = [_msg(i) for i in range(1, 26)]
    with patch(
        "app.services.topic_rebundle_service._message_mirror_bucket",
        side_effect=lambda m: getattr(m, "_bucket", "photo"),
    ):
        plan = plan_topic_rebundle_batches(loose, album_size=10, allow_partial=False)
    assert plan["full_albums"] == 2
    assert plan["partial_albums"] == 0
    assert plan["leftover_singles"] == 5
    assert all(len(b) >= 10 for b in plan["batches"])


def test_plan_separates_photo_and_video_partials():
    loose = [_msg(i) for i in range(1, 4)] + [
        _msg(100 + i, bucket="video") for i in range(1, 3)
    ]
    with patch(
        "app.services.topic_rebundle_service._message_mirror_bucket",
        side_effect=lambda m: getattr(m, "_bucket", "photo"),
    ):
        plan = plan_topic_rebundle_batches(loose, album_size=10, allow_partial=True)
    assert plan["full_albums"] == 0
    assert plan["partial_albums"] == 2
    assert plan["items_in_albums"] == 5


def test_format_preview_mentions_partial():
    text = format_topic_rebundle_summary(
        {
            "dry_run": True,
            "loose_count": 25,
            "full_albums": 2,
            "partial_albums": 1,
            "leftover_singles": 0,
            "album_size": 10,
            "allow_partial": True,
            "delete_sources": True,
        },
        html=False,
    )
    assert "partial" in text.lower()
    assert "25 loose" in text
    assert "deleted" in text.lower()


def test_format_done_mentions_deleted_sources():
    text = format_topic_rebundle_summary(
        {
            "dry_run": False,
            "albums_posted": 3,
            "partial_posted": 1,
            "album_size": 10,
            "delete_sources": True,
            "sources_deleted": 25,
        },
        html=False,
    )
    assert "deleted 25" in text.lower()


def test_topic_rebundle_delete_sources_default_on(monkeypatch):
    from app.services.topic_rebundle_service import topic_rebundle_delete_sources

    monkeypatch.delenv("TBCC_TOPIC_REBUNDLE_DELETE_SOURCES", raising=False)
    assert topic_rebundle_delete_sources() is True
    monkeypatch.setenv("TBCC_TOPIC_REBUNDLE_DELETE_SOURCES", "0")
    assert topic_rebundle_delete_sources() is False


def test_topic_rebundle_album_size_default():
    assert topic_rebundle_album_size() == 10
