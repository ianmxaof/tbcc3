#!/usr/bin/env python3
"""
Import legacy AI zip packs into the payment bot Digital packs catalog.

Each zip becomes an active bundle (bot_section=packs) at $3 / 250⭐ / crypto.
Promo: 3 sample images extracted from the zip → /static/promo/ for Telegram albums.

  cd tbcc/backend
  py -3.13 scripts/seed_ai_curated_packs.py --source-dir "C:\\...\\AOF AI PACKS"
  py -3.13 scripts/seed_ai_curated_packs.py --source-dir /opt/tbcc/pack-source --execute

On island: copy zips to /opt/tbcc/pack-source, then exec in api container (TBCC_BUNDLE_DIR=/uploads/bundles).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.models.subscription_plan import SubscriptionPlan
from app.services.bundle_parts import save_bundle_parts
from app.services.bundle_storage import (
    MAX_BUNDLE_ZIP_BYTES,
    bundle_zip_nth_path,
    ensure_bundle_dir,
    is_zip_magic,
)
from app.services.promo_storage import ensure_promo_dir

DEFAULT_SOURCE = Path(r"C:\Users\ianmp\Downloads\tbcc\AOF NETWORK\AOF RESOURCES (ZIPS)\AOF AI PACKS")
PACK_PREFIX = "AI Pack — "
PRICE_USD = 3.0
PROMO_COUNT = 3
IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})


def usd_to_stars(usd: float, *, stars_per_usd: float = 0.012) -> int:
    return max(1, int(round(float(usd) / float(stars_per_usd))))

_PART_RE = re.compile(r"^(?P<base>.+)_part_(?P<num>\d+)$", re.I)


def _public_base_url() -> str:
    return (
        (os.getenv("TBCC_PROMO_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("TBCC_PUBLIC_API_BASE_URL") or "").strip()
        or (os.getenv("TBCC_API_URL") or "").strip()
        or "http://127.0.0.1:8000"
    ).rstrip("/")


def humanize_stem(stem: str) -> str:
    s = stem.replace("_", " ").replace("-", " ")
    s = re.sub(r"\btbcc\b", "TBCC", s, flags=re.I)
    s = re.sub(r"\baof\b", "AOF", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    return s.title()


def _sale_blurb(display: str, price_usd: float) -> str:
    return (
        f"<b>{display}</b> — operator-curated AI fantasy set.\n"
        f"${price_usd:.0f} one-shot · zip to DM after payment.\n"
        "Pay with ⭐ Stars, crypto, or card when Gumroad SKU is wired.\n"
        "Samples below are pulled straight from the vault — full pack is larger."
    )


def group_zip_products(source: Path) -> list[tuple[str, str, list[Path]]]:
    """Return [(product_key, display_name, ordered_part_paths)]."""
    if not source.is_dir():
        raise FileNotFoundError(source)

    singles: dict[str, Path] = {}
    parts: dict[str, dict[int, Path]] = {}

    for p in sorted(source.glob("*.zip")):
        stem = p.stem
        m = _PART_RE.match(stem)
        if m:
            base = m.group("base")
            num = int(m.group("num"))
            parts.setdefault(base, {})[num] = p
        else:
            singles[stem] = p

    out: list[tuple[str, str, list[Path]]] = []
    seen: set[str] = set()

    for base, num_map in sorted(parts.items()):
        ordered = [num_map[k] for k in sorted(num_map.keys())]
        display = humanize_stem(base)
        out.append((base, display, ordered))
        seen.add(base)
        singles.pop(base, None)

    for stem, path in sorted(singles.items()):
        if stem in seen:
            continue
        # Skip monolithic zip when split parts already imported
        part_key = stem
        if part_key in parts:
            continue
        display = humanize_stem(stem)
        out.append((stem, display, [path]))

    return out


def _image_members(zf: zipfile.ZipFile) -> list[str]:
    names = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        if Path(info.filename).suffix.lower() in IMAGE_EXTS and info.file_size > 8_000:
            names.append(info.filename)
    names.sort(key=lambda n: (len(n), n))
    if len(names) >= PROMO_COUNT:
        step = max(1, len(names) // PROMO_COUNT)
        return [names[i * step] for i in range(PROMO_COUNT)]
    return names[:PROMO_COUNT]


def extract_promo_samples(zip_path: Path, slug: str) -> list[str]:
    """Extract up to 3 images; return public HTTPS URLs."""
    promo_dir = ensure_promo_dir()
    urls: list[str] = []
    base = _public_base_url()
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = _image_members(zf)
            for i, member in enumerate(members[:PROMO_COUNT]):
                ext = Path(member).suffix.lower() or ".jpg"
                out_name = f"pack-{slug}-{i + 1}{ext}"
                out_path = promo_dir / out_name
                data = zf.read(member)
                if len(data) > 8 * 1024 * 1024:
                    continue
                out_path.write_bytes(data)
                urls.append(f"{base}/static/promo/{out_name}")
    except zipfile.BadZipFile:
        return []
    return urls


def _plan_name(display: str) -> str:
    return f"{PACK_PREFIX}{display}"


def _find_plan(db, name: str) -> SubscriptionPlan | None:
    return db.query(SubscriptionPlan).filter(SubscriptionPlan.name == name).first()


def _copy_zip_parts(plan_id: int, part_paths: list[Path], *, execute: bool) -> list[str]:
    ensure_bundle_dir()
    filenames: list[str] = []
    for i, src in enumerate(part_paths):
        raw = src.read_bytes()
        if not is_zip_magic(raw[:512]):
            raise ValueError(f"not a zip: {src.name}")
        if len(raw) > MAX_BUNDLE_ZIP_BYTES:
            raise ValueError(f"zip part too large for Telegram ({src.name}): {len(raw)} bytes")
        fn = src.name[:500]
        filenames.append(fn)
        if execute:
            dest = bundle_zip_nth_path(plan_id, i)
            dest.write_bytes(raw)
    return filenames


def seed_pack(
    db,
    *,
    product_key: str,
    display: str,
    part_paths: list[Path],
    price_usd: float,
    execute: bool,
    report: dict,
) -> None:
    name = _plan_name(display)
    stars = usd_to_stars(price_usd, stars_per_usd=float(os.getenv("TBCC_STARS_USD_PER_STAR") or "0.012"))
    slug = re.sub(r"[^a-z0-9]+", "-", product_key.lower()).strip("-")[:48] or "pack"
    entry: dict = {
        "name": name,
        "parts": [p.name for p in part_paths],
        "price_usd": price_usd,
        "stars": stars,
    }

    for p in part_paths:
        if p.stat().st_size > MAX_BUNDLE_ZIP_BYTES:
            entry["status"] = "skipped_part_too_large"
            report["packs"].append(entry)
            return

    plan = _find_plan(db, name)
    if not plan:
        entry["status"] = "would_create" if not execute else "created"
        if execute:
            plan = SubscriptionPlan(
                name=name,
                price_stars=stars,
                duration_days=0,
                description=_sale_blurb(display, price_usd),
                description_variations_json=json.dumps(
                    [
                        f"Legacy AI vault — {display}. Instant zip DM.",
                        f"${price_usd:.0f} · {stars}⭐ · crypto checkout live.",
                    ]
                ),
                is_active=True,
                product_type="bundle",
                bot_section="packs",
                nowpayments_price_usd=float(PRICE_USD),
                nowpayments_allow_any_currency=True,
                nowpayments_pay_currency=(os.getenv("TBCC_NOWPAYMENTS_PAY_CURRENCY") or "usdttrc20"),
            )
            db.add(plan)
            db.flush()
        else:
            report["packs"].append(entry)
            return
    else:
        entry["status"] = "updated" if execute else "exists"
        entry["plan_id"] = plan.id
        if execute:
            plan.price_stars = stars
            plan.nowpayments_price_usd = float(price_usd)
            plan.is_active = True
            plan.product_type = "bundle"
            plan.bot_section = "packs"
            plan.description = _sale_blurb(display, price_usd)

    pid = int(plan.id)
    entry["plan_id"] = pid

    promo_urls: list[str] = []
    if execute:
        promo_urls = extract_promo_samples(part_paths[0], slug)
    if promo_urls:
        entry["promo_urls"] = len(promo_urls)
        if execute:
            plan.promo_image_url = promo_urls[0]
            plan.promo_image_urls_json = json.dumps(promo_urls[:5])

    if execute:
        filenames = _copy_zip_parts(pid, part_paths, execute=True)
        save_bundle_parts(plan, filenames)
        from app.services.zip_promo_inject import inject_promo_into_zip_path

        for i in range(len(filenames)):
            inject_promo_into_zip_path(bundle_zip_nth_path(pid, i), db)

    report["packs"].append(entry)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed AI curated packs from zip directory")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--price-usd", type=float, default=PRICE_USD)
    args = parser.parse_args()

    products = group_zip_products(args.source_dir.resolve())
    report: dict = {"source": str(args.source_dir), "execute": args.execute, "packs": []}

    db = SessionLocal()
    try:
        for key, display, parts in products:
            try:
                seed_pack(
                    db,
                    product_key=key,
                    display=display,
                    part_paths=parts,
                    price_usd=float(args.price_usd),
                    execute=args.execute,
                    report=report,
                )
            except Exception as e:
                report["packs"].append({"name": display, "status": "error", "error": str(e)})
        if args.execute:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
