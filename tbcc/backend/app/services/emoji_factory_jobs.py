"""Stage browser uploads and run emoji-factory split (+ optional Telegram upload)."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from app.services.import_pipeline import tbcc_run_dir
from app.services.media_frame_sample import ffmpeg_available

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".gif"}
ALLOWED_SUFFIXES = IMAGE_SUFFIXES | VIDEO_SUFFIXES
MAX_UPLOAD_BYTES = 80 * 1024 * 1024
MAX_ANIMATED_LOOP_SEC = 3.0
MAX_VIDEO_SOURCE_SEC = 10.0


def emoji_factory_jobs_dir() -> Path:
    d = tbcc_run_dir() / "emoji-factory-jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_job_dir() -> Path:
    job_id = uuid.uuid4().hex[:12]
    out = emoji_factory_jobs_dir() / job_id
    out.mkdir(parents=True, exist_ok=True)
    return out


def slug_short_name_base(filename: str) -> str:
    from app.services.emoji_pack_telethon import slug_short_name_base as _slug

    return _slug(Path(filename).stem)


def _emoji_factory_root() -> Path:
    return Path(__file__).resolve().parents[3] / "services" / "emoji-factory"


def _import_pipeline():
    import sys

    root = _emoji_factory_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from emoji_factory.pipeline import run_pipeline

    return run_pipeline


def _import_ffmpeg():
    import sys

    root = _emoji_factory_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from emoji_factory.ffmpeg_util import probe_video_size, run_ffmpeg

    return probe_video_size, run_ffmpeg


def probe_duration_sec(path: Path) -> float | None:
    import shutil
    import subprocess

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        out = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
        return float((out.stdout or "").strip())
    except Exception:
        return None


def prepare_master_video(
    source: Path,
    work_dir: Path,
    *,
    loop_sec: float,
    static: bool,
) -> Path:
    """Convert images to MP4; trim long videos to loop_sec (animated) or one frame (static)."""
    _, run_ffmpeg = _import_ffmpeg()
    suf = source.suffix.lower()
    out = work_dir / "master.mp4"

    if suf in IMAGE_SUFFIXES:
        duration = 0.1 if static else min(loop_sec, MAX_ANIMATED_LOOP_SEC)
        run_ffmpeg(
            [
                "-y",
                "-loop",
                "1",
                "-i",
                str(source),
                "-t",
                str(max(0.1, duration)),
                "-vf",
                "fps=30",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-an",
                str(out),
            ]
        )
        return out

    if suf not in VIDEO_SUFFIXES:
        raise ValueError(f"Unsupported file type: {suf}")

    dur = probe_duration_sec(source)
    if dur is not None and dur > MAX_VIDEO_SOURCE_SEC:
        raise ValueError(
            f"Video is {dur:.1f}s — max {MAX_VIDEO_SOURCE_SEC:.0f}s source length. Trim before upload or use a shorter clip."
        )

    trim_to = 0.1 if static else min(loop_sec, MAX_ANIMATED_LOOP_SEC)
    if dur is not None and dur > trim_to + 0.05:
        run_ffmpeg(
            [
                "-y",
                "-i",
                str(source),
                "-t",
                str(trim_to),
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-an",
                str(out),
            ]
        )
        return out

    shutil.copy2(source, out)
    return out


def run_create_from_upload(
    *,
    uploaded_path: Path,
    original_filename: str,
    cols: int,
    rows: int,
    tile_px: int,
    margin_pct: float,
    loop_sec: float,
    crf: int,
    static: bool,
    job_dir: Path | None = None,
) -> dict:
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg not on PATH — install ffmpeg and retry")

    suf = Path(original_filename).suffix.lower()
    if suf not in ALLOWED_SUFFIXES:
        raise ValueError(f"Unsupported file type {suf}. Use PNG/JPG/WebP or MP4/MOV/WebM/GIF.")

    size = uploaded_path.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise ValueError(f"File too large ({size // (1024 * 1024)} MB). Max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")

    if not static and loop_sec > MAX_ANIMATED_LOOP_SEC:
        raise ValueError(f"Animated loop max {MAX_ANIMATED_LOOP_SEC:.0f}s (Telegram custom emoji guideline).")

    job_dir = job_dir.resolve() if job_dir is not None else new_job_dir()
    job_dir.mkdir(parents=True, exist_ok=True)

    pack_dir = job_dir / "pack-out"
    pack_dir.mkdir(parents=True, exist_ok=True)

    staged = job_dir / f"upload{suf}"
    if uploaded_path.resolve() != staged.resolve():
        shutil.copy2(uploaded_path, staged)

    master = prepare_master_video(staged, job_dir, loop_sec=loop_sec, static=static)
    run_pipeline = _import_pipeline()
    manifest = run_pipeline(
        input_path=master,
        out_dir=pack_dir,
        cols=cols,
        rows=rows,
        tile_px=tile_px,
        margin_pct=margin_pct,
        loop_sec=min(loop_sec, MAX_ANIMATED_LOOP_SEC) if not static else loop_sec,
        crf=crf,
        static=static,
    )

    import json

    data = json.loads(manifest.read_text(encoding="utf-8"))
    over = sum(1 for t in data.get("tiles", []) if t.get("over_soft_limit"))
    return {
        "job_id": job_dir.name,
        "manifest_path": str(manifest),
        "out_dir": str(pack_dir),
        "tile_count": len(data.get("tiles", [])),
        "over_soft_limit": over,
        "suggested_short_name": slug_short_name_base(original_filename),
        "cols": cols,
        "rows": rows,
    }
