"""
Low-CPU AOF preprocess + flat lane routing for watch-folder organizes.

When sidecar/page tags resolve a lane, skip CLIP/NSFW. Watermark+rename once
unless ``aof_preprocessed`` is already true.
"""

from __future__ import annotations

import logging
import os
import random
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _is_truthy(raw: str | None, *, default: bool = False) -> bool:
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def watch_aof_lane_folders_enabled() -> bool:
    """Default ON — disk folders like ``AOF MILFGILF`` under the watch library root."""
    return _is_truthy(os.environ.get("TBCC_WATCH_AOF_LANE_FOLDERS"), default=True)


def watch_aof_inbox_preprocess_enabled() -> bool:
    """Watermark + AOF rename for bare inbox drops (skip when sidecar preprocessed)."""
    return _is_truthy(os.environ.get("TBCC_WATCH_AOF_PREPROCESS"), default=True)


def watch_aof_fast_mode() -> bool:
    """
    Hot-path mode for local firehose backlog drains: skip the watermark pass and
    clamp watch/hub debounce+stable waits (I6/I8). AOF rename still runs — cheap.
    """
    return _is_truthy(os.environ.get("TBCC_WATCH_AOF_FAST"), default=False)


def _tags_from_meta(meta: dict[str, Any] | None) -> list[str]:
    if not meta:
        return []
    raw = meta.get("tags")
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    if isinstance(raw, str) and raw.strip():
        return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    return []


def resolve_lane_from_meta(meta: dict[str, Any] | None) -> str | None:
    from app.services.aof_lane_tag_map import resolve_lane_key

    if not meta:
        return None
    preferred = meta.get("lane_key") or meta.get("network_key") or meta.get("pool_key")
    return resolve_lane_key(_tags_from_meta(meta), preferred=str(preferred) if preferred else None)


def aof_library_subdir(category: str, meta: dict[str, Any] | None) -> str | None:
    """
    Flat lane folder under library root for Images/Videos when enabled.
    Returns None to fall back to legacy Images/… CLIP path (or category-only).
    """
    if not watch_aof_lane_folders_enabled():
        return None
    if category not in ("Images", "Videos"):
        return None
    from app.services.aof_lane_tag_map import lane_folder_name

    lane = resolve_lane_from_meta(meta)
    return lane_folder_name(lane)  # Unsorted when no lane


def preprocess_inbox_media(src: Path, meta: dict[str, Any] | None) -> tuple[Path, dict[str, Any]]:
    """
    Watermark + AOF rename when not already preprocessed.
    Returns (working_path, updated_meta). May rename ``src`` in place.
    """
    from app.services.aof_lane_tag_map import aof_filename_for_path, is_aof_branded_filename, resolve_lane_key
    from app.services.watch_folder_nsfw import remove_watch_sidecar, write_watch_sidecar

    out_meta: dict[str, Any] = dict(meta or {})
    working = src

    if out_meta.get("aof_preprocessed") is True or not watch_aof_inbox_preprocess_enabled():
        if not out_meta.get("lane_key"):
            lane = resolve_lane_key(_tags_from_meta(out_meta), preferred=out_meta.get("lane_key"))
            if lane:
                out_meta["lane_key"] = lane
        return working, out_meta

    # Watermark (images + videos when ffmpeg/size ok) — skipped on the fast hot path (I8)
    if watch_aof_fast_mode():
        out_meta["watermark_skipped"] = "fast_mode"
    else:
        try:
            from app.services.local_media_watermark import is_media_path, watermark_file

            if is_media_path(working):
                wm = watermark_file(working)
                if wm.ok and wm.changed:
                    out_meta["watermark_applied"] = True
                elif wm.ok:
                    out_meta["watermark_applied"] = out_meta.get("watermark_applied", False)
                else:
                    out_meta["watermark_skipped"] = wm.message
        except Exception as e:
            logger.warning("watch aof watermark skipped %s: %s", working.name, e)
            out_meta["watermark_skipped"] = str(e)

    # AOF rename
    if not is_aof_branded_filename(working.name):
        hint = str(out_meta.get("name") or out_meta.get("profile") or working.stem)
        new_name = aof_filename_for_path(working, name_hint=hint, index=random.randint(1, 99999))
        dest = working.with_name(new_name)
        if dest.exists():
            dest = working.with_name(aof_filename_for_path(working, name_hint=hint, index=random.randint(1, 99999)))
        try:
            # Drop old sidecar before rename; rewrite after
            remove_watch_sidecar(working)
            working.rename(dest)
            working = dest
            out_meta["aof_renamed"] = True
            out_meta["source_file"] = working.name
        except OSError as e:
            logger.warning("watch aof rename failed %s: %s", working.name, e)
            out_meta["aof_rename_error"] = str(e)

    lane = resolve_lane_key(_tags_from_meta(out_meta), preferred=out_meta.get("lane_key"))
    if lane:
        out_meta["lane_key"] = lane
    # Only mark done when watermark landed (or soft-disabled). Hard failures retry next pass.
    skipped = str(out_meta.get("watermark_skipped") or "").lower()
    soft_skip = any(tok in skipped for tok in ("disabled", "force_skip", "skip_watermark", "not enabled"))
    if out_meta.get("watermark_applied") is True or soft_skip:
        out_meta["aof_preprocessed"] = True
    elif skipped:
        out_meta["aof_preprocessed"] = False
    else:
        # Non-media / nothing to watermark
        out_meta["aof_preprocessed"] = True
    out_meta["source_file"] = working.name

    # Best-effort sidecar refresh beside working file (organizer may move later)
    try:
        write_watch_sidecar(working, out_meta)
    except Exception:
        pass

    return working, out_meta
