"""
Bootstrap loot card CENTER bands from AOF AI POOL (photos → disk).

Creates three ContentPools for future curation + writes stills into:
  loot_tier_cards/centers/low|high|godroll/

  cd tbcc/backend
  py -3 scripts/export_ai_pool_to_loot_centers.py           # dry-run
  py -3 scripts/export_ai_pool_to_loot_centers.py --execute # download + write
  py -3 scripts/export_ai_pool_to_loot_centers.py --execute --per-band 40
"""

from __future__ import annotations

import argparse
import asyncio
import io
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.content_pool import ContentPool
from app.models.media import Media
from app.services.local_media_storage import is_local_pool_media, read_local_media_bytes
from app.services.loot_tier_card_assets import (
    CENTER_BAND_GODROLL,
    CENTER_BAND_HIGH,
    CENTER_BAND_LOW,
    CENTER_BANDS,
    center_band_for_tier,
    centers_dir,
    centers_root,
    ensure_center_band_dirs,
)
from app.services.media_sniff import sniff_media_kind

SOURCE_POOL = "AOF AI POOL"

# Dedicated loot card face pools (dashboard curation later)
CARD_POOLS: dict[str, str] = {
    CENTER_BAND_LOW: "LOOT CARD — LOW",
    CENTER_BAND_HIGH: "LOOT CARD — HIGH",
    CENTER_BAND_GODROLL: "LOOT CARD — GODROLL",
}

# Rough split of a shuffled photo list across bands (must sum to 1.0)
BAND_WEIGHTS = {
    CENTER_BAND_LOW: 0.55,  # tiers 1–5 most common
    CENTER_BAND_HIGH: 0.35,
    CENTER_BAND_GODROLL: 0.10,
}

LOOT_GROUP_CHANNEL_ID = 8


def _get_or_create_pool(db: Session, name: str) -> ContentPool:
    row = db.query(ContentPool).filter(ContentPool.name == name).first()
    if row:
        return row
    row = ContentPool(
        name=name,
        channel_id=LOOT_GROUP_CHANNEL_ID,
        album_size=1,
        interval_minutes=0,
        auto_post_enabled=False,
        randomize_queue=True,
    )
    db.add(row)
    db.flush()
    return row


def _clone_media(src: Media, dest_pool_id: int) -> Media:
    return Media(
        telegram_message_id=int(src.telegram_message_id or 0),
        file_id=src.file_id,
        file_unique_id=src.file_unique_id,
        media_type=src.media_type,
        source_channel=src.source_channel,
        pool_id=int(dest_pool_id),
        tags=src.tags,
        status="approved",
        nsfw_tier=getattr(src, "nsfw_tier", None),
        classification_json=getattr(src, "classification_json", None),
    )


def _ext_for_bytes(data: bytes) -> str:
    kind, ext = sniff_media_kind(data)
    if kind == "video":
        return "mp4"
    if ext and ext != "bin":
        return ext
    return "jpg"


async def _download_row_bytes(row: Media) -> bytes | None:
    if is_local_pool_media(row) or str(getattr(row, "file_id", "") or "").startswith("local:"):
        data = read_local_media_bytes(row)
        return data or None
    tg_id = int(getattr(row, "telegram_message_id", 0) or 0)
    if tg_id <= 0:
        return None
    from app.services.telegram_admin import run_telegram_io

    async def _fn(storage) -> bytes:
        raw = await storage.client.get_messages("me", ids=tg_id)
        if isinstance(raw, list):
            msg = next((m for m in raw if m is not None), None)
        else:
            msg = raw
        if not msg or not getattr(msg, "media", None):
            raise ValueError(f"Saved message {tg_id} missing")
        buf = io.BytesIO()
        await storage.client.download_media(msg, file=buf)
        data = buf.getvalue()
        if not data:
            raise ValueError(f"Empty download {tg_id}")
        return data

    try:
        return await asyncio.wait_for(run_telegram_io(_fn), timeout=45.0)
    except Exception as e:
        print(f"  skip media id={row.id}: {e}")
        return None


def _migrate_legacy_tier_folders() -> None:
    """Move centers/t1..t10 seeds into band folders if bands are empty."""
    root = centers_root()
    ensure_center_band_dirs()
    for t in range(1, 11):
        legacy = root / f"t{t}"
        if not legacy.is_dir():
            continue
        band = center_band_for_tier(t)
        dest = centers_dir(band=band)
        for p in legacy.iterdir():
            if not p.is_file() or p.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            target = dest / f"migrated-t{t}-{p.name}"
            if target.exists():
                continue
            shutil.copy2(p, target)
            print(f"migrated {p} -> {target.name}")


def _split_into_bands(rows: list[Media], *, per_band: int | None, rng: random.Random) -> dict[str, list[Media]]:
    shuffled = list(rows)
    rng.shuffle(shuffled)
    n = len(shuffled)
    if n == 0:
        return {b: [] for b in CENTER_BANDS}

    # Target counts from weights, then clamp with --per-band
    targets = {
        CENTER_BAND_LOW: int(round(n * BAND_WEIGHTS[CENTER_BAND_LOW])),
        CENTER_BAND_HIGH: int(round(n * BAND_WEIGHTS[CENTER_BAND_HIGH])),
        CENTER_BAND_GODROLL: 0,
    }
    targets[CENTER_BAND_GODROLL] = max(0, n - targets[CENTER_BAND_LOW] - targets[CENTER_BAND_HIGH])
    if per_band is not None:
        for b in CENTER_BANDS:
            targets[b] = min(targets[b], int(per_band))

    out: dict[str, list[Media]] = {b: [] for b in CENTER_BANDS}
    i = 0
    for band in CENTER_BANDS:
        take = targets[band]
        out[band] = shuffled[i : i + take]
        i += take
    # leftover → low
    if i < n and (per_band is None or len(out[CENTER_BAND_LOW]) < per_band):
        out[CENTER_BAND_LOW].extend(shuffled[i:])
    return out


async def _run(*, execute: bool, per_band: int | None, seed: int) -> int:
    ensure_center_band_dirs()
    _migrate_legacy_tier_folders()

    db = SessionLocal()
    try:
        src_pool = db.query(ContentPool).filter(ContentPool.name == SOURCE_POOL).first()
        if not src_pool:
            print(f"ERROR: pool not found: {SOURCE_POOL}")
            return 1

        photos = (
            db.query(Media)
            .filter(
                Media.pool_id == int(src_pool.id),
                Media.status == "approved",
                Media.media_type == "photo",
            )
            .order_by(Media.id.asc())
            .all()
        )
        print(f"source {SOURCE_POOL} id={src_pool.id} approved photos={len(photos)}")

        rng = random.Random(seed)
        by_band = _split_into_bands(photos, per_band=per_band, rng=rng)
        for band, rows in by_band.items():
            print(f"  plan {band}: {len(rows)} photos -> {CARD_POOLS[band]}")

        if not execute:
            print("dry-run only (pass --execute to download + write)")
            return 0

        card_pools = {band: _get_or_create_pool(db, CARD_POOLS[band]) for band in CENTER_BANDS}
        db.commit()

        written = {b: 0 for b in CENTER_BANDS}
        cloned = {b: 0 for b in CENTER_BANDS}

        for band, rows in by_band.items():
            dest_pool = card_pools[band]
            dest_dir = centers_dir(band=band)
            existing_uids = {
                str(r.file_unique_id)
                for r in db.query(Media.file_unique_id)
                .filter(Media.pool_id == int(dest_pool.id))
                .all()
                if r[0]
            }

            for row in rows:
                uid = str(row.file_unique_id or "")
                # DB clone for dashboard (optional inventory)
                if uid and uid not in existing_uids:
                    db.add(_clone_media(row, int(dest_pool.id)))
                    existing_uids.add(uid)
                    cloned[band] += 1

                data = await _download_row_bytes(row)
                if not data:
                    continue
                kind, _ = sniff_media_kind(data)
                if kind == "video":
                    continue
                ext = _ext_for_bytes(data)
                fname = f"ai-{row.id}.{ext}"
                path = dest_dir / fname
                if path.exists() and path.stat().st_size > 0:
                    continue
                path.write_bytes(data)
                written[band] += 1
                print(f"  wrote {band}/{fname} ({len(data)} bytes)")

            db.commit()

        print("done:")
        for band in CENTER_BANDS:
            print(f"  {band}: disk+{written[band]} db_clone+{cloned[band]} dir={centers_dir(band=band)}")
        return 0
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="Download + write (default dry-run)")
    ap.add_argument("--per-band", type=int, default=None, help="Max photos per band")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    raise SystemExit(asyncio.run(_run(execute=args.execute, per_band=args.per_band, seed=args.seed)))


if __name__ == "__main__":
    main()
