"""Extract pack preview stills from MEGA folders into AOF PACKS — Promo pool."""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.media import Media
from app.services.aof_packs_post_copy import PACK_LABEL_TAG_PREFIX, PACK_MOD_TAG_PREFIX, attach_preview_media_to_modifier
from app.services.local_media_storage import store_pool_media_from_bytes
from app.services.mega_pack_naming import extract_pack_theme, slug_pack_label

logger = logging.getLogger(__name__)

_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"})
_VIDEO_EXTS = frozenset({".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv", ".flv"})
_SKIP_NAME_PARTS = (
    "readme",
    "read_me",
    "aof_network",
    "aof network",
    "telegram",
    "discord",
    "logo",
    "banner",
    "promo",
    "join",
    "link",
    "onlyfans",
    "gigafans",
    "plugleak",
    "premium",
    "stash",
)


def pack_preview_max_images() -> int:
    raw = (os.getenv("TBCC_MEGA_PACK_PREVIEW_MAX") or "5").strip()
    try:
        return max(1, min(8, int(raw)))
    except ValueError:
        return 5


def pack_preview_max_depth() -> int:
    raw = (os.getenv("TBCC_MEGA_PACK_PREVIEW_MAX_DEPTH") or "4").strip()
    try:
        return max(1, min(8, int(raw)))
    except ValueError:
        return 4


def _should_skip_preview_filename(name: str) -> bool:
    low = (name or "").lower()
    if not low:
        return True
    if any(v in low for v in _VIDEO_EXTS):
        return True
    return any(k in low for k in _SKIP_NAME_PARTS)


def _pick_preview_candidates(files: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    images = []
    for item in files:
        name = str(item.get("Name") or item.get("Path") or "").strip()
        if not name:
            continue
        base = Path(name).name
        if _should_skip_preview_filename(base):
            continue
        ext = Path(name).suffix.lower()
        if ext not in _IMAGE_EXTS:
            continue
        size = int(item.get("Size") or 0)
        images.append({"path": name.replace("\\", "/"), "size": size, "name": base})

    if not images:
        return []

    # Prefer larger stills; spread across subfolders when possible.
    images.sort(key=lambda x: (-x["size"], x["path"].lower()))
    picked: list[dict[str, Any]] = []
    seen_dirs: set[str] = set()
    for row in images:
        parent = row["path"].rsplit("/", 1)[0] if "/" in row["path"] else ""
        if parent in seen_dirs and len(picked) >= 2:
            continue
        picked.append(row)
        seen_dirs.add(parent)
        if len(picked) >= limit:
            break

    if len(picked) < limit:
        for row in images:
            if row in picked:
                continue
            picked.append(row)
            if len(picked) >= limit:
                break
    return picked


def import_pack_preview_images(
    db: Session,
    *,
    folder_name: str,
    pool_id: int,
    modifier_id: int | None = None,
    theme: str | None = None,
    execute: bool = True,
) -> dict[str, Any]:
    """
    Download image stills from a MEGA pack folder → AOF PACKS — Promo pool.
    Auto-approves rows and tags them for PACKS channel albums.
    """
    from app.services.mega_rclone_client import (
        download_folder_file_bytes_rclone,
        list_folder_files_json_rclone,
    )

    limit = pack_preview_max_images()
    depth = pack_preview_max_depth()
    files = list_folder_files_json_rclone(folder_name, max_depth=depth)
    candidates = _pick_preview_candidates(files, limit=limit)

    if not candidates:
        return {"ok": True, "imported": 0, "media_ids": [], "reason": "no_images_found"}

    if not execute:
        return {
            "ok": True,
            "dry_run": True,
            "would_import": len(candidates),
            "samples": [c["path"] for c in candidates[:limit]],
        }

    theme_label = theme or extract_pack_theme(folder_name)
    slug = slug_pack_label(theme_label)
    label_tag = f"{PACK_LABEL_TAG_PREFIX}{slug}" if slug else ""
    mod_tag = f"{PACK_MOD_TAG_PREFIX}{modifier_id}" if modifier_id else ""

    imported: list[int] = []
    for row in candidates:
        try:
            data = download_folder_file_bytes_rclone(folder_name, row["path"])
        except Exception as exc:
            logger.warning("preview download failed %s/%s: %s", folder_name, row["path"], exc)
            continue
        if not data or len(data) < 2048:
            continue
        source = f"mega_pack_preview:{folder_name[:80]}:{row['path'][:120]}"
        media = store_pool_media_from_bytes(
            data,
            "photo",
            source,
            pool_id,
            db,
            skip_watermark=False,
        )
        if not media:
            existing = (
                db.query(Media.id)
                .filter(
                    Media.pool_id == pool_id,
                    Media.source_channel == source[:512],
                )
                .first()
            )
            if existing:
                imported.append(int(existing[0]))
            continue
        tags = [t for t in (mod_tag, label_tag, "pack_preview") if t]
        media.tags = ",".join(tags)[:512]
        media.status = "approved"
        db.commit()
        imported.append(int(media.id))

    if modifier_id and imported:
        from app.models.loot import LootModifier

        mod = db.query(LootModifier).filter(LootModifier.id == modifier_id).first()
        if mod:
            attach_preview_media_to_modifier(db, mod, imported, pool_id=pool_id)

    if not imported and candidates and execute:
        bulk = _import_previews_via_bulk_copy(
            db,
            folder_name=folder_name,
            pool_id=pool_id,
            modifier_id=modifier_id,
            theme_label=theme_label,
            slug=slug,
            label_tag=label_tag,
            mod_tag=mod_tag,
            limit=limit,
            depth=depth,
        )
        imported = bulk.get("media_ids") or []

    reason = None if imported else ("no_images_found" if not candidates else "download_failed")
    return {"ok": True, "imported": len(imported), "media_ids": imported, "reason": reason}


def _import_previews_via_bulk_copy(
    db: Session,
    *,
    folder_name: str,
    pool_id: int,
    modifier_id: int | None,
    theme_label: str,
    slug: str,
    label_tag: str,
    mod_tag: str,
    limit: int,
    depth: int,
) -> dict[str, Any]:
    """Fallback when per-file rclone copyto fails on paths with special characters."""
    from app.services.mega_rclone_client import _run_rclone, mega_rclone_remote

    staging = Path(tempfile.mkdtemp(prefix="tbcc_pack_preview_"))
    try:
        transfers = (os.getenv("TBCC_RCLONE_TRANSFERS") or "4").strip()
        args = [
            "copy",
            f"{mega_rclone_remote()}{folder_name}",
            str(staging),
            "--fast-list",
            "--transfers",
            transfers,
            "--max-depth",
            str(max(1, depth)),
            "--max-size",
            "25M",
        ]
        for pat in ("*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp", "*.bmp"):
            args.extend(["--include", pat])
        proc = _run_rclone(args, timeout=300.0)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "rclone copy failed")[:500])

        images = [
            p
            for p in staging.rglob("*")
            if p.is_file() and p.suffix.lower() in _IMAGE_EXTS and p.stat().st_size >= 2048
        ]
        if not images:
            return {"media_ids": []}
        images.sort(key=lambda p: p.stat().st_size, reverse=True)
        imported: list[int] = []
        for path in images[:limit]:
            data = path.read_bytes()
            rel = path.relative_to(staging).as_posix()
            source = f"mega_pack_preview:{folder_name[:80]}:{rel[:120]}"
            media = store_pool_media_from_bytes(
                data,
                "photo",
                source,
                pool_id,
                db,
                skip_watermark=False,
            )
            if not media:
                existing = (
                    db.query(Media.id)
                    .filter(
                        Media.pool_id == pool_id,
                        Media.source_channel == source[:512],
                    )
                    .first()
                )
                if existing:
                    imported.append(int(existing[0]))
                continue
            tags = [t for t in (mod_tag, label_tag, "pack_preview") if t]
            media.tags = ",".join(tags)[:512]
            media.status = "approved"
            db.commit()
            imported.append(int(media.id))

        if modifier_id and imported:
            from app.models.loot import LootModifier

            mod = db.query(LootModifier).filter(LootModifier.id == modifier_id).first()
            if mod:
                attach_preview_media_to_modifier(db, mod, imported, pool_id=pool_id)
        return {"media_ids": imported}
    except Exception as exc:
        logger.warning("bulk preview import failed %s: %s", folder_name, exc)
        return {"media_ids": []}
    finally:
        shutil.rmtree(staging, ignore_errors=True)
