"""Tests for dashboard thumbnail warm queue + ingest cache helpers."""

from unittest.mock import MagicMock, patch

import pytest


def test_queue_thumbnail_warm_skips_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("TBCC_MEDIA_CACHE_DIR", str(tmp_path))
    from app.services.media_cache_storage import write_thumb_atomic
    from app.services.thumb_cache_service import queue_thumbnail_warm

    write_thumb_atomic(42, b"jpeg-bytes")
    with patch("app.workers.thumbnail_warm_worker.warm_media_thumbnails") as mock_delay:
        with patch("app.services.thumb_cache_service._open_import_jobs_above_threshold", return_value=False):
            out = queue_thumbnail_warm([42, 99])
    assert out["already_cached"] == 1
    assert out["queued"] == 1
    mock_delay.delay.assert_called_once_with([99])


def test_queue_thumbnail_warm_pauses_when_imports_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("TBCC_MEDIA_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("TBCC_THUMBNAIL_WARM_PAUSE_WHEN_IMPORTS", "1")
    from app.services.thumb_cache_service import queue_thumbnail_warm

    with patch("app.workers.thumbnail_warm_worker.warm_media_thumbnails") as mock_delay:
        with patch("app.services.thumb_cache_service._open_import_jobs_above_threshold", return_value=True):
            with patch(
                "app.services.post_scheduler.posting_stalled_for_admission",
                return_value=False,
            ):
                out = queue_thumbnail_warm([7, 8])
    assert out["queued"] == 0
    assert out.get("paused") is True
    assert out.get("reason") == "imports_pending"
    mock_delay.delay.assert_not_called()


def test_api_thumbnail_telegram_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TBCC_THUMBNAIL_API_TELEGRAM", raising=False)
    from app.services.thumb_cache_service import api_thumbnail_telegram_enabled

    assert api_thumbnail_telegram_enabled() is False


def test_bytes_to_thumbnail_jpeg_from_png():
    from PIL import Image
    import io

    from app.services.thumb_cache_service import bytes_to_thumbnail_jpeg

    buf = io.BytesIO()
    Image.new("RGB", (64, 48), color=(10, 20, 30)).save(buf, format="PNG")
    jpeg = bytes_to_thumbnail_jpeg(buf.getvalue())
    assert jpeg is not None
    assert jpeg[:2] == b"\xff\xd8"


@pytest.mark.asyncio
async def test_cache_thumb_from_message_writes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TBCC_MEDIA_CACHE_DIR", str(tmp_path))
    from app.services.thumb_cache_service import cache_thumb_from_message

    client = MagicMock()

    async def fake_download(_msg, file=None, thumb=None):
        file.write(b"\xff\xd8\xff\xd9")

    client.download_media = fake_download
    msg = MagicMock()
    msg.media = object()
    ok = await cache_thumb_from_message(client, msg, 7)
    assert ok is True
    from app.services.media_cache_storage import cached_thumb_path

    assert cached_thumb_path(7) is not None
