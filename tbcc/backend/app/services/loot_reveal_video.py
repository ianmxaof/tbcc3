"""Animated loot reveal cards — ffmpeg loop + composited card overlay."""

from __future__ import annotations

import logging
import os
import random
import subprocess
import tempfile
from pathlib import Path

from app.services.media_frame_sample import ffmpeg_available

logger = logging.getLogger(__name__)


def loot_reveal_video_enabled() -> bool:
    raw = (os.getenv("TBCC_LOOT_REVEAL_VIDEO") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def loot_reveal_video_celery_enabled() -> bool:
    """Offload encode to Celery worker (island CPU isolation)."""
    raw = (os.getenv("TBCC_LOOT_REVEAL_VIDEO_CELERY") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def reveal_video_duration_s() -> float:
    raw = (os.getenv("TBCC_LOOT_REVEAL_VIDEO_SECONDS") or "4").strip()
    try:
        return max(2.0, min(8.0, float(raw)))
    except ValueError:
        return 4.0


def reveal_video_size() -> int:
    raw = (os.getenv("TBCC_LOOT_REVEAL_VIDEO_SIZE") or "512").strip()
    try:
        return max(320, min(1080, int(raw)))
    except ValueError:
        return 512


def reveal_video_encode_timeout_s() -> int:
    raw = (os.getenv("TBCC_LOOT_REVEAL_VIDEO_TIMEOUT_S") or "12").strip()
    try:
        return max(5, min(45, int(raw)))
    except ValueError:
        return 12


def backgrounds_dir() -> Path:
    from app.services.loot_tier_card_assets import loot_tier_card_dir

    override = (os.getenv("TBCC_LOOT_CARD_BACKGROUNDS_DIR") or "").strip()
    if override:
        return Path(override)
    return loot_tier_card_dir() / "backgrounds"


def list_background_loops() -> list[Path]:
    root = backgrounds_dir()
    if not root.is_dir():
        return []
    out: list[Path] = []
    for ext in (".mp4", ".webm", ".mov"):
        out.extend(sorted(root.glob(f"*{ext}")))
    return [p for p in out if p.is_file() and p.stat().st_size > 1024]


def pick_background_loop(rng: random.Random | None = None) -> Path | None:
    loops = list_background_loops()
    if not loops:
        return None
    r = rng or random.Random()
    return r.choice(loops)


def mux_card_on_loop(
    card_jpeg: bytes,
    background: Path,
    *,
    duration_s: float | None = None,
    size: int | None = None,
) -> bytes | None:
    """
    Composite unique card JPEG over a looping background → MP4 (H.264, yuv420p).
    Background is scaled/cropped to square; card centered on top.
    """
    if not card_jpeg or not background.is_file():
        return None
    if not ffmpeg_available():
        logger.debug("loot reveal video: ffmpeg unavailable")
        return None

    dur = duration_s if duration_s is not None else reveal_video_duration_s()
    dim = size if size is not None else reveal_video_size()
    timeout = reveal_video_encode_timeout_s()

    with tempfile.TemporaryDirectory(prefix="tbcc_loot_reveal_") as td:
        td_path = Path(td)
        card_path = td_path / "card.jpg"
        out_path = td_path / "reveal.mp4"
        card_path.write_bytes(card_jpeg)

        # Loop background, trim to duration, scale square, overlay card centered.
        filt = (
            f"[0:v]scale={dim}:{dim}:force_original_aspect_ratio=increase,"
            f"crop={dim}:{dim},fps=24,trim=duration={dur},setpts=PTS-STARTPTS[bg];"
            f"[1:v]scale={dim}:{dim}:force_original_aspect_ratio=decrease[card];"
            f"[bg][card]overlay=(W-w)/2:(H-h)/2:format=auto[v]"
        )
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(background),
            "-i",
            str(card_path),
            "-filter_complex",
            filt,
            "-map",
            "[v]",
            "-t",
            str(dur),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
        try:
            subprocess.run(cmd, timeout=timeout, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"").decode("utf-8", errors="replace")[:500]
            logger.warning("loot reveal ffmpeg failed: %s", stderr)
            return None
        except subprocess.TimeoutExpired:
            logger.warning("loot reveal ffmpeg timed out after %ss", timeout)
            return None
        if not out_path.is_file() or out_path.stat().st_size < 4096:
            return None
        return out_path.read_bytes()


def compose_reveal_card_mp4(
    card_jpeg: bytes,
    *,
    rng: random.Random | None = None,
    background: Path | None = None,
) -> tuple[bytes | None, str]:
    """Wrap card bytes + random loop → MP4."""
    if not loot_reveal_video_enabled():
        return None, "disabled"
    bg = background or pick_background_loop(rng)
    if bg is None:
        return None, "no_background_loops"
    data = mux_card_on_loop(card_jpeg, bg)
    if not data:
        return None, f"encode_failed:{bg.name}"
    return data, f"mp4 bg={bg.name} dur={reveal_video_duration_s()}s"
