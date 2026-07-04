"""Scan local folders and burn AOF promo watermarks into images/videos."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.services.media_watermark import (
    WatermarkApplyConfig,
    ffmpeg_available,
    maybe_apply_media_watermark,
    watermark_config_context,
    watermark_enabled,
    watermark_max_video_mb,
    watermark_text,
)

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".webm", ".avi", ".mkv"})
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


@dataclass
class MediaScan:
    root: Path | None
    files: list[Path] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.files)


@dataclass
class WatermarkFileResult:
    path: Path
    changed: bool
    ok: bool
    message: str = ""


@dataclass
class WatermarkBatchResult:
    results: list[WatermarkFileResult] = field(default_factory=list)

    @property
    def ok(self) -> int:
        return sum(1 for r in self.results if r.ok and r.changed)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.ok and not r.changed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.ok)

    def summary(self) -> str:
        return f"{self.ok} watermarked, {self.skipped} unchanged, {self.failed} failed"


def is_media_path(path: Path | str) -> bool:
    return Path(path).suffix.lower() in MEDIA_EXTENSIONS


def media_type_hint(path: Path | str) -> str:
    return "video" if Path(path).suffix.lower() in VIDEO_EXTENSIONS else "photo"


def ensure_local_watermark_defaults() -> None:
    """Best-effort defaults for headless/local runs when tbcc/.env omits watermark vars."""
    if not (os.getenv("TBCC_WATERMARK_TEXT") or "").strip() and not watermark_text():
        os.environ.setdefault("TBCC_WATERMARK_TEXT", "t.me/aofmainhub")
    os.environ.setdefault("TBCC_WATERMARK_ENABLED", "1")
    # Explorer context menu / local CLI: subtle burn-in (server pipeline default is 0.045).
    os.environ.setdefault("TBCC_WATERMARK_SIZE_RATIO", "0.024")
    if os.name == "nt" and not (os.getenv("TBCC_WATERMARK_FONT_PATH") or "").strip():
        os.environ.setdefault("TBCC_WATERMARK_FONT_PATH", "C:/Windows/Fonts/arial.ttf")


def resolve_apply_config(db=None) -> WatermarkApplyConfig:
    ensure_local_watermark_defaults()
    if db is not None:
        try:
            from app.services.watermark_settings_effective import build_apply_config

            return build_apply_config(db)
        except Exception:
            logger.debug("resolve_apply_config: DB settings unavailable", exc_info=True)
    from app.services.media_watermark import _default_env_config

    return _default_env_config()


def scan_media_folder(
    folder: str | Path,
    *,
    recursive: bool = True,
    max_files: int | None = None,
) -> MediaScan:
    root = Path(folder).expanduser().resolve()
    scan = MediaScan(root=root)
    if not root.is_dir():
        scan.skipped.append(f"not_a_directory:{root}")
        return scan

    iterator = root.rglob("*") if recursive else root.iterdir()
    found: list[Path] = []
    for path in sorted(iterator):
        if not path.is_file():
            continue
        if path.suffix.lower() not in MEDIA_EXTENSIONS:
            if recursive or path.parent == root:
                rel = path.relative_to(root)
                scan.skipped.append(str(rel))
            continue
        found.append(path)

    if max_files is not None and len(found) > max_files:
        scan.skipped.extend(str(p.relative_to(root)) for p in found[max_files:])
        found = found[:max_files]
    scan.files = found
    return scan


def collect_media_paths(paths: list[str | Path]) -> MediaScan:
    files: list[Path] = []
    skipped: list[str] = []
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        if path.is_dir():
            nested = scan_media_folder(path, recursive=True)
            files.extend(nested.files)
            skipped.extend(nested.skipped)
            continue
        if not path.is_file():
            skipped.append(f"not_found:{path}")
            continue
        if not is_media_path(path):
            skipped.append(f"unsupported:{path.name}")
            continue
        files.append(path)
    return MediaScan(root=None, files=files, skipped=skipped)


def _video_too_large(path: Path, raw: bytes, *, max_video_mb: int | None) -> bool:
    if media_type_hint(path) != "video":
        return False
    limit = watermark_max_video_mb() if max_video_mb is None else max(1, int(max_video_mb))
    return len(raw) > limit * 1024 * 1024


def watermark_file(
    path: Path | str,
    *,
    config: WatermarkApplyConfig | None = None,
    output_path: Path | None = None,
    max_video_mb: int | None = None,
) -> WatermarkFileResult:
    src = Path(path).expanduser().resolve()
    if not src.is_file():
        return WatermarkFileResult(src, changed=False, ok=False, message="not found")
    if not is_media_path(src):
        return WatermarkFileResult(src, changed=False, ok=False, message="unsupported type")

    cfg = config or resolve_apply_config()
    if not cfg.enabled or cfg.skip or not cfg.texts:
        return WatermarkFileResult(src, changed=False, ok=False, message="watermark disabled or no text")
    if media_type_hint(src) == "video" and not ffmpeg_available():
        return WatermarkFileResult(src, changed=False, ok=False, message="ffmpeg unavailable")

    try:
        raw = src.read_bytes()
    except OSError as e:
        return WatermarkFileResult(src, changed=False, ok=False, message=str(e))

    if _video_too_large(src, raw, max_video_mb=max_video_mb):
        mb = len(raw) // (1024 * 1024)
        limit = watermark_max_video_mb() if max_video_mb is None else max_video_mb
        return WatermarkFileResult(src, changed=False, ok=False, message=f"video too large ({mb} MB > {limit} MB)")

    hint = media_type_hint(src)
    with watermark_config_context(cfg):
        out = maybe_apply_media_watermark(raw, hint)

    if out == raw:
        return WatermarkFileResult(src, changed=False, ok=True, message="unchanged")

    dest = output_path.expanduser().resolve() if output_path else src
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(out)
    except OSError as e:
        return WatermarkFileResult(src, changed=False, ok=False, message=str(e))

    before_mb = len(raw) // (1024 * 1024)
    after_mb = len(out) // (1024 * 1024)
    return WatermarkFileResult(
        src,
        changed=True,
        ok=True,
        message=f"{before_mb} MB -> {after_mb} MB" + (f" -> {dest.name}" if dest != src else ""),
    )


def watermark_paths(
    paths: list[Path],
    *,
    config: WatermarkApplyConfig | None = None,
    output_dir: Path | None = None,
    max_video_mb: int | None = None,
    on_progress: Callable[[int, int, WatermarkFileResult], None] | None = None,
) -> WatermarkBatchResult:
    cfg = config or resolve_apply_config()
    batch = WatermarkBatchResult()
    total = len(paths)
    for index, path in enumerate(paths, start=1):
        out_path: Path | None = None
        if output_dir is not None:
            out_path = output_dir / path.name
        result = watermark_file(
            path,
            config=cfg,
            output_path=out_path,
            max_video_mb=max_video_mb,
        )
        batch.results.append(result)
        if on_progress:
            on_progress(index, total, result)
    return batch


def format_scan_report(scan: MediaScan, *, list_limit: int = 40) -> str:
    lines: list[str] = []
    if scan.root is not None:
        lines.append(f"Folder: {scan.root}")
    lines.append(f"Media files: {len(scan.files)}")
    if scan.skipped:
        lines.append(f"Skipped entries: {len(scan.skipped)}")

    images = sum(1 for p in scan.files if media_type_hint(p) == "photo")
    videos = len(scan.files) - images
    lines.append(f"  images: {images}, videos: {videos}")

    cfg = resolve_apply_config()
    lines.append(f"Watermark: {cfg.texts[0] if cfg.texts else '(none)'}")
    lines.append(f"Enabled: {watermark_enabled() and bool(cfg.texts)} · ffmpeg: {ffmpeg_available()}")

    for path in scan.files[:list_limit]:
        size_mb = path.stat().st_size / (1024 * 1024)
        kind = media_type_hint(path)
        lines.append(f"  [{kind}] {path.name} ({size_mb:.1f} MB)")
    if len(scan.files) > list_limit:
        lines.append(f"  … and {len(scan.files) - list_limit} more")
    return "\n".join(lines)
