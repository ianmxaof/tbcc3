"""Export Buffer bulk-import CSV from AOF caption pools + R2 promo images.

Run from tbcc/backend:

  py -3.13 scripts/export_buffer_csv.py --channel primary --count 200
  py -3.13 scripts/export_buffer_csv.py --channel secondary --count 100
  py -3.13 scripts/export_buffer_csv.py --channel ig --count 60
  py -3.13 scripts/export_buffer_csv.py --all

Output matches Buffer UI bulk upload columns:
  Text, Image URL, Tags, Posting Time (YYYY-MM-DD HH:MM, America/Los_Angeles)

Posting times use safe PT slots with >=4h gaps per channel.
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.aof_x_buffer_armory import AOF_X_BUFFER_ARMORY_TEMPLATES  # noqa: E402
from app.data.aof_x_buffer_native_pool import AOF_X_BUFFER_NATIVE_POOL  # noqa: E402
from app.services.aof_social_links import (  # noqa: E402
    affiliate_botynude_url,
    affiliate_drawai_url,
    affiliate_undress_primary_url,
    fill_armory_template,
)
from app.services.buffer_surface_caption import build_instagram_caption, teaser_without_urls  # noqa: E402
from app.services.buffer_x_caption import finalize_buffer_x_caption  # noqa: E402
from app.services.buffer_x_hashtags import append_x_hashtags  # noqa: E402
from app.services.r2_promo_upload import load_pool_entries  # noqa: E402

PT = ZoneInfo("America/Los_Angeles")

CHANNEL_PROFILES: dict[str, dict] = {
    "primary": {
        "tag": "x-primary",
        "slots": [(11, 30), (14, 30), (19, 0)],
        "posts_per_day": 3,
        "for_x": True,
    },
    "secondary": {
        "tag": "x-secondary",
        "slots": [(12, 0), (15, 30), (20, 30)],
        "posts_per_day": 3,
        "for_x": True,
    },
    "ig": {
        "tag": "ig",
        "slots": [(12, 30)],
        "posts_per_day": 1,
        "for_x": False,
    },
}

_AFFILIATES = [
    affiliate_undress_primary_url(),
    affiliate_drawai_url(),
    affiliate_botynude_url(),
]


def _template_pool() -> list[str]:
    texts: list[str] = []
    for row in AOF_X_BUFFER_NATIVE_POOL:
        t = (row.get("text") or "").strip()
        if t:
            texts.append(t)
    for row in AOF_X_BUFFER_ARMORY_TEMPLATES:
        t = (row.get("text") or "").strip()
        if t:
            texts.append(t)
    return texts


def _image_urls() -> list[str]:
    urls: list[str] = []
    for row in load_pool_entries():
        u = str(row.get("direct_url") or row.get("url") or "").strip()
        if u.startswith("https://"):
            urls.append(u)
    return urls or [""]


def _build_x_caption(template: str, *, affiliate_idx: int) -> str:
    import os

    os.environ["TBCC_BUFFER_X_LINK_CYCLE"] = "0"
    aff = _AFFILIATES[affiliate_idx % len(_AFFILIATES)]
    raw = fill_armory_template(
        template.replace("{affiliate}", aff),
        utm_source="buffer",
        utm_medium="x",
        utm_campaign="csv_batch",
        for_x=True,
    )
    text = finalize_buffer_x_caption(raw, advance_link_cycle=False)
    text = append_x_hashtags(text, max_chars=280)
    if len(text) > 280:
        text = text[:277].rstrip() + "…"
    return text


def _iter_post_times(
    *,
    count: int,
    slots: list[tuple[int, int]],
    posts_per_day: int,
    start: date,
) -> list[datetime]:
    """Yield timezone-aware PT datetimes, max posts_per_day per calendar day."""
    out: list[datetime] = []
    day = start
    slot_idx = 0
    posted_today = 0
    while len(out) < count:
        if posted_today >= posts_per_day:
            day += timedelta(days=1)
            posted_today = 0
            slot_idx = 0
        hour, minute = slots[slot_idx % len(slots)]
        slot_idx += 1
        posted_today += 1
        dt = datetime.combine(day, time(hour, minute), tzinfo=PT)
        if dt <= datetime.now(PT):
            continue
        out.append(dt)
    return out


def _caption_variants(count: int, *, for_x: bool, rng: random.Random) -> list[str]:
    pool = _template_pool()
    if not pool:
        raise SystemExit("No caption templates in pool")
    rng.shuffle(pool)
    variants: list[str] = []
    for i in range(count):
        tpl = pool[i % len(pool)]
        if for_x:
            cap = _build_x_caption(tpl, affiliate_idx=i)
        else:
            teaser = teaser_without_urls(fill_armory_template(tpl, for_x=False), max_len=200)
            cap = build_instagram_caption(teaser=teaser or None, utm_campaign="csv_batch")
        if not cap.strip():
            continue
        variants.append(cap)
    if len(variants) < count:
        raise SystemExit(f"Only generated {len(variants)} captions (need {count})")
    return variants


def export_csv(
    *,
    channel: str,
    count: int,
    output: Path,
    start: date,
    seed: int,
) -> dict:
    profile = CHANNEL_PROFILES[channel]
    rng = random.Random(seed)
    images = _image_urls()
    rng.shuffle(images)
    captions = _caption_variants(count, for_x=profile["for_x"], rng=rng)
    times = _iter_post_times(
        count=count,
        slots=profile["slots"],
        posts_per_day=profile["posts_per_day"],
        start=start,
    )
    tag = profile["tag"]
    rows: list[dict[str, str]] = []
    for i in range(count):
        img = images[i % len(images)] if images else ""
        posting = times[i].strftime("%Y-%m-%d %H:%M")
        rows.append(
            {
                "Text": captions[i],
                "Image URL": img,
                "Tags": tag,
                "Posting Time": posting,
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Text", "Image URL", "Tags", "Posting Time"],
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        writer.writerows(rows)
    return {
        "channel": channel,
        "count": len(rows),
        "output": str(output),
        "first": rows[0]["Posting Time"] if rows else None,
        "last": rows[-1]["Posting Time"] if rows else None,
        "tag": tag,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Export Buffer bulk-import CSV")
    p.add_argument(
        "--channel",
        choices=sorted(CHANNEL_PROFILES),
        help="Channel profile (primary=wizardstick69, secondary=PowerCoreAi, ig)",
    )
    p.add_argument("--count", type=int, default=200)
    p.add_argument("--start", default="", help="Start date YYYY-MM-DD (default: tomorrow PT)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--output",
        default="",
        help="Output CSV path (default: ~/Downloads/buffer_import_<channel>.csv)",
    )
    p.add_argument("--all", action="store_true", help="Export primary(200), secondary(100), ig(60)")
    args = p.parse_args()

    if args.start.strip():
        start = date.fromisoformat(args.start.strip())
    else:
        start = (datetime.now(PT) + timedelta(days=1)).date()

    jobs: list[tuple[str, int]] = []
    if args.all:
        jobs = [("primary", 200), ("secondary", 100), ("ig", 60)]
    elif args.channel:
        jobs = [(args.channel, args.count)]
    else:
        p.error("Pass --channel or --all")

    downloads = Path.home() / "Downloads"
    reports = []
    for ch, n in jobs:
        out = Path(args.output) if args.output and len(jobs) == 1 else downloads / f"buffer_import_{ch}.csv"
        reports.append(export_csv(channel=ch, count=n, output=out, start=start, seed=args.seed + hash(ch) % 1000))

    for r in reports:
        print(
            f"{r['channel']}: {r['count']} rows -> {r['output']} "
            f"({r['first']} .. {r['last']}) tag={r['tag']}"
        )


if __name__ == "__main__":
    main()
