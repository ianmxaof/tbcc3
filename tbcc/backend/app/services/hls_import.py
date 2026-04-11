"""Download HLS (.m3u8) or DASH (.mpd) streams to a single MP4 via ffmpeg (when available on PATH)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)

# Hard cap to avoid runaway downloads (adjust via env)
HLS_MAX_BYTES_DEFAULT = int(os.environ.get("TBCC_HLS_MAX_BYTES", str(500 * 1024 * 1024)))


def hls_or_dash_url_to_mp4_bytes(
    url: str,
    *,
    referer: str | None = None,
    timeout_sec: int = 900,
    max_bytes: int | None = None,
) -> bytes:
    """
    Use ffmpeg to mux the stream to MP4 in a temp file, then read bytes.
    Fails clearly if ffmpeg is missing or the URL is not a supported manifest.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is not on PATH; install ffmpeg to import HLS/DASH URLs.")

    cap = max_bytes if max_bytes is not None else HLS_MAX_BYTES_DEFAULT
    ulow = (url or "").lower()
    if not (".m3u8" in ulow or ".mpd" in ulow):
        raise ValueError("URL must look like an HLS (.m3u8) or DASH (.mpd) manifest.")

    path_out = ""
    try:
        fd, path_out = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        headers: list[str] = []
        if referer:
            headers.extend(["-headers", f"Referer: {referer}\r\n"])
        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            *headers,
            "-i",
            url,
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            path_out,
        ]
        cp = subprocess.run(cmd, capture_output=True, timeout=timeout_sec, check=False)
        if cp.returncode != 0:
            err = (cp.stderr or b"").decode("utf-8", errors="replace")[:800]
            raise RuntimeError(f"ffmpeg failed ({cp.returncode}): {err or 'no stderr'}")
        if not os.path.isfile(path_out):
            raise RuntimeError("ffmpeg produced no output file")
        size = os.path.getsize(path_out)
        if size > cap:
            raise RuntimeError(f"Output exceeds max size ({cap} bytes)")
        with open(path_out, "rb") as f:
            return f.read()
    finally:
        try:
            if path_out and os.path.isfile(path_out):
                os.unlink(path_out)
        except OSError:
            pass
