"""Extract a single JPEG frame from video bytes via ffmpeg (for NSFW classify)."""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def ffmpeg_available() -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        return True
    except Exception:
        return False


def extract_video_frame_jpeg(video_bytes: bytes, *, seek_s: float = 1.0, max_edge: int = 768) -> bytes | None:
    if not video_bytes or len(video_bytes) < 4096:
        return None
    if not ffmpeg_available():
        logger.debug("ffmpeg not available for frame sample")
        return None
    timeout = int(os.getenv("TBCC_FFMPEG_FRAME_TIMEOUT", "45"))
    with tempfile.TemporaryDirectory(prefix="tbcc_frame_") as td:
        inp = Path(td) / "in.bin"
        out = Path(td) / "frame.jpg"
        inp.write_bytes(video_bytes[:200_000_000])
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(max(0.0, seek_s)),
            "-i",
            str(inp),
            "-vframes",
            "1",
            "-vf",
            f"scale='min({max_edge},iw)':-2",
            "-q:v",
            "4",
            "-y",
            str(out),
        ]
        try:
            subprocess.run(cmd, timeout=timeout, check=True, capture_output=True)
        except Exception as e:
            logger.debug("ffmpeg frame extract failed: %s", e)
            return None
        if not out.is_file() or out.stat().st_size < 64:
            return None
        return out.read_bytes()
