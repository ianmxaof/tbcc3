"""Thin ffmpeg wrappers."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def ffmpeg_on_path() -> bool:
    return shutil.which("ffmpeg") is not None


def run_ffmpeg(args: list[str], *, timeout: int = 600) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", *args]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or "").strip()
        raise RuntimeError(err or "ffmpeg failed") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"ffmpeg timed out after {timeout}s") from e


def probe_video_size(path: Path) -> tuple[int, int]:
    """Return (width, height) via ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe not on PATH (install ffmpeg bundle)")
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        str(path),
    ]
    try:
        out = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
    except subprocess.CalledProcessError as e:
        raise RuntimeError((e.stderr or "").strip() or "ffprobe failed") from e
    line = (out.stdout or "").strip().splitlines()[0]
    w, h = line.split("x")
    return int(w), int(h)
