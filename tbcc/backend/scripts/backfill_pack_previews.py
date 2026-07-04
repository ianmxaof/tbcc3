#!/usr/bin/env python3
"""
Backfill AOF PACKS preview stills for existing pack-pool modifiers from MEGA account folders.

Matches loot_modifiers → MEGA folder by theme/label (incl. -TME AOFMAINHUB names), then runs
import_pack_preview_images for rows missing preview_ids.

Usage:
  cd tbcc/backend
  py -3.13 scripts/backfill_pack_previews.py
  py -3.13 scripts/backfill_pack_previews.py --execute
  py -3.13 scripts/backfill_pack_previews.py --execute --modifier-id 24
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.models.content_pool import ContentPool
from app.services.aof_packs_post_copy import parse_pack_source_note
from app.services.loot_pack_pool import POOL_NAME, list_active_pack_pool_modifiers
from app.services.mega_pack_naming import extract_pack_theme, slug_pack_label
from app.services.mega_pack_previews import import_pack_preview_images
from app.services.mega_rclone_client import (
    list_mega_folders_rclone,
    should_skip_folder,
    use_mega_rclone,
    verify_rclone_mega_access,
)

_DEFAULT_EXPORT = _backend.parent / "docs" / "samples" / "mega_pack_folders.txt"


def _mega_keys(url: str) -> set[str]:
    keys: set[str] = set()
    raw = (url or "").strip()
    if not raw:
        return keys
    for m in re.finditer(r"/folder/([^#?/]+)", raw, re.I):
        keys.add(m.group(1))
    for m in re.finditer(r"#!([^!]+)!", raw):
        keys.add(m.group(1))
    return keys


def _load_export_folder_map(path: Path) -> dict[str, str]:
    """MEGA folder id → folder label from export file."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = (line or "").strip()
        if not raw or raw.startswith("#"):
            continue
        if "|" in raw:
            label, _, url = raw.partition("|")
            label = label.strip()
            url = url.strip()
        else:
            label, url = "", raw
        for key in _mega_keys(url):
            out[key] = label or out.get(key, "")
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _label_theme(label: str) -> str:
    raw = (label or "").strip()
    low = raw.lower()
    if not raw or low in ("mega.nz", "mega.co.nz"):
        return ""
    if low.startswith("aof pack") or low.startswith("rentry"):
        return ""
    if re.match(r"^mega\s+\d", low):
        return ""
    return extract_pack_theme(raw)


def _match_folder(
    label: str,
    folders: list[str],
    *,
    destination_url: str = "",
    export_key_to_label: dict[str, str] | None = None,
) -> str | None:
    if not folders:
        return None
    by_lower = {f.lower(): f for f in folders}

    for key in _mega_keys(destination_url):
        export_label = (export_key_to_label or {}).get(key, "").strip()
        if export_label.lower() in by_lower:
            return by_lower[export_label.lower()]
        if export_label:
            hit = _match_folder(export_label, folders)
            if hit:
                return hit

    label_stripped = (label or "").strip()
    if label_stripped.lower() in by_lower:
        return by_lower[label_stripped.lower()]

    theme = _label_theme(label_stripped)
    if not theme:
        # Size hint: "AOF Pack — 13.7GB" → match folder containing 13.7GB
        m = re.search(r"(\d+(?:\.\d+)?)\s*gb", label_stripped, re.I)
        if m:
            gb = float(m.group(1))
            gb_variants = {f"{gb:.1f}".rstrip("0").rstrip(".")}
            if gb >= 10:
                gb_variants.add(f"{gb:.0f}")
            for fn in folders:
                fn_compact = fn.replace(" ", "").lower()
                for gv in gb_variants:
                    if f"{gv}gb" in fn_compact:
                        return fn
        return None

    slug = slug_pack_label(theme)
    tnorm = _norm(theme)

    by_slug: dict[str, list[str]] = {}
    for fn in folders:
        fs = slug_pack_label(extract_pack_theme(fn))
        by_slug.setdefault(fs, []).append(fn)
        by_slug.setdefault(_norm(extract_pack_theme(fn)), []).append(fn)

    if slug in by_slug and len(by_slug[slug]) == 1:
        return by_slug[slug][0]
    if tnorm in by_slug and len(by_slug[tnorm]) == 1:
        return by_slug[tnorm][0]

    for fn in folders:
        fnorm = _norm(fn)
        if tnorm and len(tnorm) >= 5 and tnorm in fnorm:
            return fn
    for fn in folders:
        if theme.lower() in fn.lower():
            return fn
    return None


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

    p = argparse.ArgumentParser(description="Backfill pack preview images from MEGA folders")
    p.add_argument("--execute", action="store_true", help="Download stills and attach preview_ids")
    p.add_argument("--modifier-id", type=int, action="append", default=[], help="Limit to modifier id(s)")
    p.add_argument("--force", action="store_true", help="Re-import even when preview_ids exist")
    p.add_argument("--export-links", type=Path, default=_DEFAULT_EXPORT, help="Export file for MEGA id → label")
    args = p.parse_args()

    if not use_mega_rclone():
        print("TBCC_MEGA_BACKEND=rclone required.", file=sys.stderr)
        raise SystemExit(1)
    verify_rclone_mega_access()

    folders = [f.name for f in list_mega_folders_rclone() if not should_skip_folder(f.name)]
    export_map = _load_export_folder_map(args.export_links)
    print(f"MEGA pack folders: {len(folders)} (export keys: {len(export_map)})")

    db = SessionLocal()
    imported_total = skipped = no_folder = no_mega = 0
    try:
        pool = db.query(ContentPool).filter(ContentPool.name == POOL_NAME).first()
        if not pool:
            print(f"Pool not found: {POOL_NAME}", file=sys.stderr)
            raise SystemExit(1)

        mods = list_active_pack_pool_modifiers(db)
        if args.modifier_id:
            wanted = {int(x) for x in args.modifier_id}
            mods = [m for m in mods if m.id in wanted]

        for mod in mods:
            meta = parse_pack_source_note(mod.source_note)
            dest = (meta.destination_url or "").lower()
            if "mega" not in dest and "mega" not in (mod.label or "").lower():
                no_mega += 1
                continue
            if meta.preview_media_ids and not args.force:
                skipped += 1
                print(f"SKIP id={mod.id} already has {len(meta.preview_media_ids)} previews")
                continue

            folder = _match_folder(
                mod.label or "",
                folders,
                destination_url=meta.destination_url or "",
                export_key_to_label=export_map,
            )
            if not folder:
                no_folder += 1
                print(f"NO_FOLDER id={mod.id} label={(mod.label or '')[:60]!r}")
                continue

            theme = extract_pack_theme(folder)
            if not args.execute:
                print(f"DRY id={mod.id} → {folder[:70]}")
                continue

            result = import_pack_preview_images(
                db,
                folder_name=folder,
                pool_id=int(pool.id),
                modifier_id=int(mod.id),
                theme=theme,
                execute=True,
            )
            n = int(result.get("imported") or 0)
            imported_total += n
            if n:
                print(f"OK id={mod.id} folder={folder[:55]} imported={n} ids={result.get('media_ids')}")
            else:
                print(f"WARN id={mod.id} folder={folder[:55]} reason={result.get('reason') or result.get('error')}")
    finally:
        db.close()

    mode = "execute" if args.execute else "dry-run"
    print(
        f"\n--- {mode}: imported_images={imported_total} skipped_has_preview={skipped} "
        f"no_mega_dest={no_mega} no_folder_match={no_folder}"
    )


if __name__ == "__main__":
    main()
