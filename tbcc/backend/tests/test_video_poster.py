"""Tests for video poster picking / near-black rejection."""

from __future__ import annotations

import io

import pytest


def _solid_jpeg(color: tuple[int, int, int], size: tuple[int, int] = (64, 64)) -> bytes:
    from PIL import Image

    im = Image.new("RGB", size, color)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def test_is_near_black_jpeg_detects_black():
    from app.services.video_poster import is_near_black_jpeg

    assert is_near_black_jpeg(_solid_jpeg((0, 0, 0))) is True
    assert is_near_black_jpeg(_solid_jpeg((8, 8, 8))) is True


def test_is_near_black_jpeg_allows_bright_frame():
    from app.services.video_poster import is_near_black_jpeg

    assert is_near_black_jpeg(_solid_jpeg((180, 120, 90))) is False


def test_shrink_telegram_thumb_jpeg_under_budget():
    from app.services.video_poster import shrink_telegram_thumb_jpeg

    big = _solid_jpeg((200, 100, 50), size=(1200, 800))
    out = shrink_telegram_thumb_jpeg(big, max_edge=320, max_bytes=20_000)
    assert out is not None
    assert len(out) <= 20_000
    assert out[:2] == b"\xff\xd8"


def test_pick_video_poster_rejects_all_black_seeks(monkeypatch):
    from app.services import video_poster as vp

    monkeypatch.setattr(
        "app.services.media_frame_sample.extract_video_frame_jpeg",
        lambda *a, **k: _solid_jpeg((2, 2, 2)),
    )
    monkeypatch.setattr(
        "app.services.media_frame_sample.ffmpeg_available",
        lambda: True,
    )
    assert vp.pick_video_poster_jpeg(b"x" * 8000) is None


def test_pick_video_poster_accepts_first_non_black(monkeypatch):
    from app.services import video_poster as vp

    calls: list[float] = []

    def fake_extract(video_bytes, *, seek_s=1.0, max_edge=768):
        calls.append(seek_s)
        if seek_s < 5:
            return _solid_jpeg((0, 0, 0))
        return _solid_jpeg((200, 80, 60))

    monkeypatch.setattr("app.services.media_frame_sample.extract_video_frame_jpeg", fake_extract)
    monkeypatch.setattr("app.services.media_frame_sample.ffmpeg_available", lambda: True)
    out = vp.pick_video_poster_jpeg(b"x" * 8000)
    assert out is not None
    assert out[:2] == b"\xff\xd8"
    assert any(s >= 5 for s in calls)


def test_prepare_video_send_file_skips_when_required(monkeypatch):
    from app.services import video_poster as vp

    monkeypatch.setattr(vp, "video_poster_required", lambda: True)
    monkeypatch.setattr(vp, "pick_video_poster_jpeg", lambda *a, **k: None)
    prep = vp.prepare_video_send_file(b"x" * 8000, media_id=99)
    assert prep.skip is True
    assert prep.skip_reason == "no_usable_poster"


def test_prepare_video_send_file_attaches_thumb(monkeypatch):
    from app.services import video_poster as vp

    thumb = _solid_jpeg((190, 100, 70))
    monkeypatch.setattr(vp, "pick_video_poster_jpeg", lambda *a, **k: thumb)
    monkeypatch.setattr(vp, "ffprobe_video_wh_duration", lambda *a, **k: (1280, 720, 42))
    monkeypatch.setattr(vp, "video_poster_required", lambda: True)
    # Avoid writing disk cache in unit test
    monkeypatch.setattr(
        "app.services.media_cache_storage.write_thumb_atomic",
        lambda *a, **k: None,
    )
    prep = vp.prepare_video_send_file(b"x" * 8000, media_id=7)
    assert prep.skip is False
    assert prep.thumb is not None
    assert prep.supports_streaming is True
    assert prep.attributes


def test_cached_thumb_is_usable_negative(tmp_path, monkeypatch):
    from app.services import media_cache_storage as mcs
    from app.services import video_poster as vp

    monkeypatch.setattr(mcs, "media_cache_root", lambda: tmp_path)
    mcs.write_negative_marker(55)
    assert vp.cached_thumb_is_usable(55) is False


def test_cached_thumb_is_usable_black_file(tmp_path, monkeypatch):
    from app.services import media_cache_storage as mcs
    from app.services import video_poster as vp

    monkeypatch.setattr(mcs, "media_cache_root", lambda: tmp_path)
    mcs.write_thumb_atomic(56, _solid_jpeg((0, 0, 0)))
    assert vp.cached_thumb_is_usable(56) is False


def test_cached_thumb_is_usable_good(tmp_path, monkeypatch):
    from app.services import media_cache_storage as mcs
    from app.services import video_poster as vp

    monkeypatch.setattr(mcs, "media_cache_root", lambda: tmp_path)
    mcs.write_thumb_atomic(57, _solid_jpeg((200, 150, 100)))
    assert vp.cached_thumb_is_usable(57) is True
