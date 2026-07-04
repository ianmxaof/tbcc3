"""Channel import timeout budget."""

from app.services.channel_import_runner import channel_import_timeout_s


def test_channel_import_timeout_videos_15():
    # 15 videos × 120s + 360s lock = 2160s (was 1260s with old limit×20 formula)
    assert channel_import_timeout_s(15, media_types="videos") == 2160


def test_channel_import_timeout_photos_15():
    assert channel_import_timeout_s(15, media_types="photos") == 1260


def test_channel_import_timeout_both_uses_video_budget():
    assert channel_import_timeout_s(15, media_types="both") == 2160


def test_channel_import_timeout_index_only_15():
    # max(120, 15×3+60) + 360 lock = 480s
    assert channel_import_timeout_s(15, media_types="videos", index_only=True) == 480
