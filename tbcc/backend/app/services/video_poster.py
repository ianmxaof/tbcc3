"""Pick a usable Telegram video poster (JPEG thumb) — reject near-black frames.

Used on scheduled/album re-uploads so Telegram does not invent a black play-button
poster from the opening frames. Also used as a light approve-time gate against
cached dashboard thumbs that are already known-bad.
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


def video_poster_required() -> bool:
    raw = (os.getenv("TBCC_VIDEO_POSTER_REQUIRED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def poster_black_mean_max() -> float:
    raw = (os.getenv("TBCC_VIDEO_POSTER_BLACK_MEAN_MAX") or "22").strip()
    try:
        return max(5.0, min(80.0, float(raw)))
    except ValueError:
        return 22.0


def poster_seek_seconds() -> list[float]:
    raw = (os.getenv("TBCC_VIDEO_POSTER_SEEKS") or "1.5,3,6,12,20").strip()
    out: list[float] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(max(0.0, float(part)))
        except ValueError:
            continue
    return out or [1.5, 3.0, 6.0, 12.0]


def jpeg_luma_stats(jpeg_bytes: bytes) -> tuple[float, float] | None:
    """Return (mean, stdev) of luma on a small grayscale sample, or None if unreadable."""
    if not jpeg_bytes or len(jpeg_bytes) < 32:
        return None
    try:
        from PIL import Image, ImageStat

        im = Image.open(io.BytesIO(jpeg_bytes))
        im = im.convert("L")
        im.thumbnail((96, 96))
        st = ImageStat.Stat(im)
        mean = float(st.mean[0]) if st.mean else 0.0
        stdev = float(st.stddev[0]) if st.stddev else 0.0
        return mean, stdev
    except Exception:
        logger.debug("jpeg luma stats failed", exc_info=True)
        return None


def is_near_black_jpeg(jpeg_bytes: bytes, *, mean_max: float | None = None) -> bool:
    """True when the frame is too dark / flat to be a useful Telegram poster."""
    stats = jpeg_luma_stats(jpeg_bytes)
    if stats is None:
        return True
    mean, stdev = stats
    limit = poster_black_mean_max() if mean_max is None else mean_max
    # Very dark, or dark+flat (solid black / near-black letterbox).
    if mean <= limit:
        return True
    if mean <= limit + 10 and stdev < 8:
        return True
    return False


def shrink_telegram_thumb_jpeg(jpeg_bytes: bytes, *, max_edge: int = 320, max_bytes: int = 20_000) -> bytes | None:
    """Telegram ignores thumbs that are too large; keep under ~20KB / 320px."""
    if not jpeg_bytes:
        return None
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(jpeg_bytes))
        im = im.convert("RGB")
        im.thumbnail((max_edge, max_edge))
        for quality in (70, 55, 40, 30):
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=quality, optimize=True)
            data = buf.getvalue()
            if len(data) <= max_bytes:
                return data
        return data if data else None
    except Exception:
        logger.debug("shrink telegram thumb failed", exc_info=True)
        return None


def pick_video_poster_jpeg(video_bytes: bytes, *, max_edge: int = 640) -> bytes | None:
    """
    Sample several seeks via ffmpeg; return first non-black frame shrunk for Telegram thumb.
    """
    from app.services.media_frame_sample import extract_video_frame_jpeg, ffmpeg_available

    if not video_bytes or len(video_bytes) < 4096:
        return None
    if not ffmpeg_available():
        return None
    for seek in poster_seek_seconds():
        frame = extract_video_frame_jpeg(video_bytes, seek_s=seek, max_edge=max_edge)
        if not frame:
            continue
        if is_near_black_jpeg(frame):
            logger.debug("video poster seek=%.1fs rejected near-black", seek)
            continue
        thumb = shrink_telegram_thumb_jpeg(frame)
        if thumb and not is_near_black_jpeg(thumb):
            return thumb
    return None


def ffprobe_video_wh_duration(video_bytes: bytes) -> tuple[int, int, int]:
    """Best-effort (w, h, duration_s). Zeros when ffprobe missing/fails."""
    import json
    import subprocess
    import tempfile
    from pathlib import Path

    if not video_bytes or len(video_bytes) < 4096:
        return 0, 0, 0
    try:
        with tempfile.TemporaryDirectory(prefix="tbcc_probe_") as td:
            inp = Path(td) / "in.bin"
            inp.write_bytes(video_bytes[:200_000_000])
            cmd = [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height:format=duration",
                "-of",
                "json",
                str(inp),
            ]
            proc = subprocess.run(cmd, capture_output=True, timeout=30, check=False)
            if proc.returncode != 0 or not proc.stdout:
                return 0, 0, 0
            data = json.loads(proc.stdout.decode("utf-8", errors="ignore") or "{}")
            streams = data.get("streams") or []
            w = h = 0
            if streams:
                w = int(streams[0].get("width") or 0)
                h = int(streams[0].get("height") or 0)
            dur_raw = (data.get("format") or {}).get("duration")
            try:
                dur = max(0, int(float(dur_raw or 0)))
            except (TypeError, ValueError):
                dur = 0
            return w, h, dur
    except Exception:
        logger.debug("ffprobe failed", exc_info=True)
        return 0, 0, 0


@dataclass
class PreparedSendFile:
    """One outbound Telethon send_file payload (photo BytesIO or video+thumb)."""

    file: io.BytesIO
    thumb: io.BytesIO | None = None
    attributes: list[Any] = field(default_factory=list)
    supports_streaming: bool = False
    mime_type: str | None = None
    skip: bool = False
    skip_reason: str | None = None
    media_id: int | None = None


def prepare_video_send_file(
    video_bytes: bytes,
    *,
    media_id: int | None = None,
    filename: str = "video.mp4",
) -> PreparedSendFile:
    """Build a video BytesIO + custom poster thumb, or mark skip if poster required and missing."""
    f = io.BytesIO(video_bytes)
    f.name = filename
    thumb_bytes = pick_video_poster_jpeg(video_bytes)
    if not thumb_bytes:
        if video_poster_required():
            return PreparedSendFile(
                file=f,
                skip=True,
                skip_reason="no_usable_poster",
                media_id=media_id,
            )
        # Soft mode: still send, Telegram invents poster (legacy).
        w, h, dur = ffprobe_video_wh_duration(video_bytes)
        from telethon.tl.types import DocumentAttributeFilename, DocumentAttributeVideo

        attrs: list[Any] = [
            DocumentAttributeVideo(
                duration=dur,
                w=w or 640,
                h=h or 360,
                supports_streaming=True,
            ),
            DocumentAttributeFilename(filename),
        ]
        return PreparedSendFile(
            file=f,
            attributes=attrs,
            supports_streaming=True,
            mime_type="video/mp4",
            media_id=media_id,
        )

    w, h, dur = ffprobe_video_wh_duration(video_bytes)
    from telethon.tl.types import DocumentAttributeFilename, DocumentAttributeVideo

    attrs = [
        DocumentAttributeVideo(
            duration=dur,
            w=w or 640,
            h=h or 360,
            supports_streaming=True,
        ),
        DocumentAttributeFilename(filename),
    ]
    thumb = io.BytesIO(thumb_bytes)
    thumb.name = "thumb.jpg"
    # Also refresh dashboard cache when we have a good poster.
    if media_id:
        try:
            from app.services.media_cache_storage import write_thumb_atomic

            write_thumb_atomic(int(media_id), thumb_bytes)
        except Exception:
            logger.debug("poster cache write skipped media_id=%s", media_id, exc_info=True)
    return PreparedSendFile(
        file=f,
        thumb=thumb,
        attributes=attrs,
        supports_streaming=True,
        mime_type="video/mp4",
        media_id=media_id,
    )


def cached_thumb_is_usable(media_id: int) -> bool | None:
    """
    True = cached thumb looks usable.
    False = known bad (negative marker or near-black cache).
    None = no cache yet (unknown).
    """
    from app.services.media_cache_storage import cached_thumb_path, negative_marker_fresh

    mid = int(media_id)
    if negative_marker_fresh(mid):
        return False
    path = cached_thumb_path(mid)
    if not path:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if is_near_black_jpeg(data):
        return False
    return True


def approve_blocks_bad_video_poster() -> bool:
    raw = (os.getenv("TBCC_APPROVE_BLOCK_BAD_VIDEO_POSTER") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")
