"""MEGA (rclone) → local staging → Erome album upload."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from app.services.erome_promo_wire import erome_watermark_required
from app.services.import_pipeline import tbcc_run_dir
from app.services.mega_rclone_client import download_mega_folder_to_local_rclone, list_mega_folders_rclone
from app.services.erome_upload_provision import load_flow_config, scan_staging_folder
from app.services.media_watermark import maybe_apply_media_watermark

logger = logging.getLogger(__name__)

_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"})


def erome_staging_dir() -> Path:
    d = tbcc_run_dir() / "erome-staging"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_folder_slug(name: str) -> str:
    slug = re.sub(r"[^\w.-]+", "_", (name or "").strip())[:80]
    return slug or "mega_pack"


def apply_aof_watermarks_to_files(files: list[Path]) -> int:
    """Burn AOF promo watermark into staged files before Erome upload."""
    if not erome_watermark_required():
        return 0
    if not files:
        return 0
    applied = 0
    for path in files:
        try:
            raw = path.read_bytes()
            ext = path.suffix.lower()
            hint = "video" if ext in {".mp4", ".mov", ".webm", ".avi", ".mkv"} else "photo"
            if hint == "video":
                max_mb = int(os.getenv("TBCC_EROME_WATERMARK_MAX_VIDEO_MB") or "80")
                if len(raw) > max_mb * 1024 * 1024:
                    logger.info("skip erome video watermark (too large): %s", path.name)
                    continue
            out = maybe_apply_media_watermark(raw, hint)
            if out != raw:
                path.write_bytes(out)
                applied += 1
        except Exception:
            logger.warning("watermark failed for %s", path, exc_info=True)
    return applied


def stage_mega_folder_for_erome(
    folder_name: str,
    *,
    max_files: int | None = None,
    dest: Path | None = None,
    max_depth: int = 4,
    watermark: bool | None = None,
) -> tuple[Path, list[Path]]:
    root = dest or (erome_staging_dir() / _safe_folder_slug(folder_name))
    copied = download_mega_folder_to_local_rclone(
        folder_name,
        root,
        max_files=max_files,
        max_depth=max_depth,
    )
    if copied == 0:
        raise RuntimeError(f"No media files copied from MEGA folder: {folder_name}")
    cfg = load_flow_config()
    scan = scan_staging_folder(root, allowed_extensions=cfg.allowed_extensions, max_files=max_files)
    if not scan.ok:
        raise RuntimeError(f"Staging empty after MEGA download: {root}")
    do_wm = erome_watermark_required() if watermark is None else watermark
    if do_wm:
        n = apply_aof_watermarks_to_files(scan.files)
        logger.info("AOF watermarks applied to %s/%s staged files", n, len(scan.files))
    return root, scan.files


def pick_smallest_mega_folder(*, limit: int = 25, max_depth: int = 2) -> list[tuple[str, int]]:
    """Return (folder_name, media_file_count) sorted ascending — debug/discovery only."""
    from app.services.mega_rclone_client import list_folder_files_json_rclone, should_skip_folder

    folders = list_mega_folders_rclone()
    scored: list[tuple[str, int]] = []
    for entry in folders[: max(limit, 1)]:
        if should_skip_folder(entry.name):
            continue
        items = list_folder_files_json_rclone(entry.name, max_depth=max_depth)
        count = 0
        for item in items:
            rel = str(item.get("Path") or item.get("Name") or "")
            if Path(rel).suffix.lower() in {
                ".jpg",
                ".jpeg",
                ".png",
                ".gif",
                ".webp",
                ".bmp",
                ".mp4",
                ".mov",
                ".webm",
                ".avi",
                ".mkv",
            }:
                count += 1
        scored.append((entry.name, count))
    scored.sort(key=lambda x: (x[1], x[0].lower()))
    return scored
