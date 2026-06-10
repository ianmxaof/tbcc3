import io
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from app.services import media_watermark as wm


def _jpeg_bytes(w: int = 320, h: int = 200) -> bytes:
    im = Image.new("RGB", (w, h), color=(40, 80, 120))
    buf = io.BytesIO()
    im.save(buf, format="JPEG")
    return buf.getvalue()


def _tiny_png() -> bytes:
    im = Image.new("RGBA", (64, 48), color=(10, 20, 30, 255))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _fake_mp4_header() -> bytes:
    """Minimal ISO BMFF header so sniff_media_kind returns video (not valid for ffmpeg)."""
    return b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41" + b"\x00" * 64


def _tiny_mp4_bytes() -> bytes | None:
    """One-frame H.264 MP4 via ffmpeg; None when ffmpeg is unavailable."""
    if not wm.ffmpeg_available():
        return None
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "tiny.mp4"
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=blue:s=64x48:d=0.2",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-pix_fmt",
                    "yuv420p",
                    "-an",
                    str(out),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
        except Exception:
            return None
        if out.is_file() and out.stat().st_size > 256:
            return out.read_bytes()
    return None


@pytest.fixture(autouse=True)
def _watermark_env(monkeypatch):
    monkeypatch.setenv("TBCC_WATERMARK_ENABLED", "1")
    monkeypatch.setenv("TBCC_WATERMARK_TEXT", "aof.test")
    monkeypatch.setenv("TBCC_WATERMARK_MODE", "fixed")
    monkeypatch.setenv("TBCC_WATERMARK_POSITION", "bottom_right")


def test_disabled_without_text(monkeypatch):
    monkeypatch.delenv("TBCC_WATERMARK_TEXT", raising=False)
    monkeypatch.delenv("TBCC_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("TBCC_PROMO_PUBLIC_BASE_URL", raising=False)
    assert wm.watermark_enabled() is False
    raw = _jpeg_bytes()
    assert wm.maybe_apply_media_watermark(raw) == raw


def test_multi_text_watermark():
    cfg = wm.WatermarkApplyConfig(
        enabled=True,
        texts=("line.one", "line.two"),
        opacity=0.6,
        color_hex="#ff0000",
        strip_previous=False,
    )
    raw = _tiny_png()
    out = wm.maybe_apply_media_watermark(raw, "photo", config=cfg)
    assert out != raw
    assert len(out) > len(raw)


def test_strip_previous_runs():
    cfg = wm.WatermarkApplyConfig(
        enabled=True,
        texts=("aof.test",),
        strip_previous=True,
    )
    raw = _tiny_png()
    out = wm.maybe_apply_media_watermark(raw, "photo", config=cfg)
    assert out != raw


def test_image_watermark_changes_bytes():
    raw = _jpeg_bytes()
    out = wm.maybe_apply_media_watermark(raw, "photo")
    assert out != raw
    assert out[:3] == b"\xff\xd8\xff"


def test_skip_context():
    raw = _jpeg_bytes()
    with wm.skip_watermark_context(True):
        assert wm.maybe_apply_media_watermark(raw) == raw


def test_rotate_positions(monkeypatch):
    monkeypatch.setenv("TBCC_WATERMARK_MODE", "rotate")
    positions = {wm._pick_position() for _ in range(10)}
    assert "bottom_right" in positions
    assert len(positions) >= 3


def test_force_skip():
    raw = _jpeg_bytes()
    assert wm.maybe_apply_media_watermark(raw, force_skip=True) == raw


def test_document_hint_photo(monkeypatch):
    monkeypatch.setenv("TBCC_WATERMARK_ENABLED", "1")
    raw = _jpeg_bytes()
    out = wm.maybe_apply_media_watermark(raw, "photo")
    assert len(out) > 100


def test_video_skips_when_ffmpeg_unavailable(monkeypatch):
    raw = _fake_mp4_header()
    monkeypatch.setattr(wm, "ffmpeg_available", lambda: False)
    out = wm.maybe_apply_media_watermark(raw, "video")
    assert out == raw


def test_video_skips_when_too_large(monkeypatch):
    raw = _fake_mp4_header() * 5000
    monkeypatch.setattr(wm, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(wm, "watermark_max_video_mb", lambda: 1)
    out = wm.maybe_apply_media_watermark(raw, "video")
    assert out == raw


def test_video_passes_through_on_ffmpeg_failure(monkeypatch):
    raw = _fake_mp4_header()
    monkeypatch.setattr(wm, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(wm, "_font_path", lambda: "C:/Windows/Fonts/arial.ttf")

    def _boom(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, "ffmpeg")

    monkeypatch.setattr(wm.subprocess, "run", _boom)
    out = wm.maybe_apply_media_watermark(raw, "video")
    assert out == raw


def test_video_skips_without_font(monkeypatch):
    raw = _fake_mp4_header()
    monkeypatch.setattr(wm, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(wm, "_font_path", lambda: "")
    out = wm.maybe_apply_media_watermark(raw, "video")
    assert out == raw


def test_video_watermark_changes_bytes_when_ffmpeg_ok(monkeypatch):
    tiny = _tiny_mp4_bytes()
    if tiny is None:
        pytest.skip("ffmpeg unavailable for integration test")
    monkeypatch.setattr(wm, "watermark_max_video_mb", lambda: 250)
    cfg = wm.WatermarkApplyConfig(
        enabled=True,
        texts=("aof.test",),
        opacity=0.8,
        color_hex="#ffffff",
        mode="fixed",
        position="bottom_right",
    )
    out = wm.maybe_apply_media_watermark(tiny, "video", config=cfg)
    assert out != tiny
    assert out[4:8] == b"ftyp"


def test_video_mocked_ffmpeg_returns_output(monkeypatch):
    raw = _fake_mp4_header()
    watermarked = raw + b"watermarked-mp4-padding" + b"\x00" * 300
    monkeypatch.setattr(wm, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(wm, "_font_path", lambda: "C:/Windows/Fonts/arial.ttf")

    def _fake_run(cmd, **_kwargs):
        out_path = Path(cmd[-1])
        out_path.write_bytes(watermarked)
        return MagicMock(returncode=0)

    monkeypatch.setattr(wm.subprocess, "run", _fake_run)
    out = wm.maybe_apply_media_watermark(raw, "video")
    assert out == watermarked
