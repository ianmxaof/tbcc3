"""Detect actual media kind from file magic bytes (overrides wrong Content-Type / URL)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)


def sniff_media_kind(data: bytes) -> tuple[str, str]:
    """
    Returns (kind, ext) where kind is one of: photo, video, gif, document.
    ext is a sensible filename extension for Telethon upload.
    """
    if not data or len(data) < 12:
        return "document", "bin"

    if data[:3] == b"\xff\xd8\xff":
        return "photo", "jpg"

    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "photo", "png"

    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WEBP":
        return "photo", "webp"

    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif", "gif"

    # MP4 / ISO BMFF
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video", "mp4"

    # WebM / Matroska EBML
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "video", "webm"

    # AVI
    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"AVI ":
        return "video", "avi"

    return "document", "bin"


def telegram_media_type_from_sniff(kind: str) -> str:
    """Map sniff kind to Media.media_type / send_file branch."""
    if kind == "video":
        return "video"
    if kind == "gif":
        return "photo"
    if kind == "photo":
        return "photo"
    return "document"


def _mp4_needs_progressive_remux(data: bytes) -> bool:
    """
    True for MPEG-DASH / CMAF style MP4: ftyp lists 'dash' and/or file contains moof (fragment) boxes.
    Those files often fail in Windows Movies & TV / Photos even though VLC plays them.
    """
    if len(data) < 32 or data[4:8] != b"ftyp":
        return False
    try:
        sz = int.from_bytes(data[0:4], "big")
    except Exception:
        return False
    if 16 <= sz <= len(data) and b"dash" in data[8:sz]:
        return True
    head = min(len(data), 524288)
    return b"moof" in data[:head]


def maybe_remux_mp4_for_playback(data: bytes) -> bytes:
    """
    If bytes are fragmented DASH/CMAF MP4, remux with ffmpeg to a progressive MP4 more players accept.
    No-op when TBCC_SKIP_MP4_REMUX=1, ffmpeg is missing, or input is already progressive.
    """
    if os.environ.get("TBCC_SKIP_MP4_REMUX") == "1":
        return data
    if not data or not _mp4_needs_progressive_remux(data):
        return data
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        logger.warning(
            "Video is MPEG-DASH-style MP4 (fragmented moof/mdat). Install ffmpeg on PATH "
            "so TBCC can remux for desktop players, or open the file in VLC / mpv."
        )
        return data
    path_in = ""
    path_out = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as fin:
            fin.write(data)
            path_in = fin.name
        fd, path_out = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        cp = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                path_in,
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                path_out,
            ],
            capture_output=True,
            timeout=900,
            check=False,
        )
        if cp.returncode != 0:
            logger.warning(
                "ffmpeg remux failed rc=%s: %s",
                cp.returncode,
                (cp.stderr or b"").decode("utf-8", errors="replace")[:800],
            )
            return data
        if not os.path.isfile(path_out) or os.path.getsize(path_out) < max(4096, len(data) // 200):
            logger.warning("ffmpeg remux produced unusable output; keeping original bytes")
            return data
        with open(path_out, "rb") as f:
            return f.read()
    except Exception as e:
        logger.warning("ffmpeg remux error: %s", e)
        return data
    finally:
        for p in (path_in, path_out):
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass
