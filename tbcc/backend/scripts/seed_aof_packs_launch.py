"""
Seed AOF PACKS channel for launch: pinned promo images + 3 hyperlinked copy variations + scraped LV links.

  cd tbcc/backend && py -3.13 scripts/seed_aof_packs_launch.py --execute
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.mega_scrape_channel_sources import AOF_PACKS_CHANNEL_ID
from app.database.session import SessionLocal
from app.models.content_pool import ContentPool
from app.models.loot import LootModifier
from app.models.media import Media
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.linkvertise_wrap import publisher_id_from_env, wrap_linkvertise_url

POOL_NAME = "AOF PACKS — Promo"
SCHED_NAME = "AOF PACKS — seed rotation"
# Approved seed promos (reuse only these until more are added)
SEED_MEDIA_IDS = (2168, 2169, 2170)

# Sophon packs resolved during direct scrape (LV-wrap for caption variety)
EXTRA_DESTINATIONS = [
    ("Milf vault", "https://drive.newsophon.com/s2/z5Ek3AemLJ658PrvbWdM"),
    ("Blowjob pack", "https://drive.newsophon.com/s2/9WEbgLrmwejr8ev10YaK"),
]


def _a_tag(lv_url: str, anchor: str) -> str:
    return f'<a href="{html.escape(lv_url, quote=True)}">{html.escape(anchor)}</a>'


def _build_captions(lv_urls: list[str], footer: str) -> list[str]:
    """Eight AOF PACKS voice variations — HTML for Telethon poster + addlist footer."""
    anchors = ("vault", "unpack", "enter", "claim", "drop", "folder", "gate", "pull")
    bodies = [
        (
            "📦 <b>AOF PACK DROP</b>\n"
            "golden fans batch — terabox folder tagged & cleared.\n"
            "you weren't invited. you clicked anyway. good."
        ),
        (
            "psy-slop parcel hour.\n"
            "another curated dump cleared the pipeline — milf lane, no filler.\n"
            "scarcity isn't cruelty. it's filtration."
        ),
        (
            "<b>PACK LIVE</b> — blowjob channel scrape, re-wrapped for AOF.\n"
            "one friction step between you and the folder. that's the seduction."
        ),
        (
            "<b>TERABOX BATCH</b> — fresh golden fans dump.\n"
            "LV gate keeps the tourists out. you already know the drill."
        ),
        (
            "milf vault hour.\n"
            "sophon folder cleared the pipeline — no filler, no apology.\n"
            "filtration is a feature."
        ),
        (
            "<b>BJ PACK</b> — curated lane drop.\n"
            "one ad step. one folder. zero regret."
        ),
        (
            "📦 <b>PIPELINE DROP</b>\n"
            "TBCC scraped it. LV wrapped it. you unlock it.\n"
            "VIP skips the line → @aofsubscriptions_bot"
        ),
        (
            "<b>MAX PACE PACK</b>\n"
            "another folder hits the feed before you finish scrolling.\n"
            "that's the point."
        ),
    ]
    out: list[str] = []
    for i, body in enumerate(bodies):
        link = lv_urls[i % len(lv_urls)]
        anchor = anchors[i % len(anchors)]
        out.append(
            f"{body}\n\n{_a_tag(link, anchor)} · VIP skips the gate → @aofsubscriptions_bot{footer}"
        )
    return out


def seed(*, execute: bool) -> dict:
    pub = publisher_id_from_env()
    report: dict = {"captions": [], "media_ids": list(SEED_MEDIA_IDS), "lv_urls": []}

    db = SessionLocal()
    try:
        pool = db.query(ContentPool).filter(ContentPool.name == POOL_NAME).first()
        if not pool:
            report["error"] = f"pool_not_found:{POOL_NAME}"
            return report
        report["pool_id"] = pool.id

        if execute:
            pool.auto_post_enabled = False
            pool.randomize_queue = True
            pool.album_size = 1

        # Primary scraped pack (GoldenFans18+ terabox) — prefer clean row (no ** typo in label/url)
        mods = (
            db.query(LootModifier)
            .filter(LootModifier.kind == "mega_pack", LootModifier.active.is_(True))
            .order_by(LootModifier.id.asc())
            .all()
        )
        mod = next((m for m in mods if m.target_url and "**" not in (m.label or "")), None) or (
            mods[0] if mods else None
        )
        if not mod or not mod.target_url:
            report["error"] = "no_mega_pack_modifier"
            return report

        lv_terabox = mod.target_url.strip().split()[0]
        lv_extra = [wrap_linkvertise_url(pub, dest) for _, dest in EXTRA_DESTINATIONS]
        lv_urls = [lv_terabox, lv_extra[0], lv_extra[1], lv_terabox, lv_extra[0], lv_extra[1], lv_terabox, lv_extra[0]]
        addlist_lv = wrap_linkvertise_url(pub, "https://t.me/addlist/r-7_7CGIkExhMDcx")
        loot_bot = "https://t.me/aof_lootgod_bot?start=loot_free"
        loot_room = "https://t.me/+NWathiLSqZ1lMzlh"
        footer = (
            "\n\n━━━━━━━━━━━━━━━━━━\n"
            "📌 <b>Join the full AOF stack</b> — one tap\n"
            f'{_a_tag(addlist_lv, "addlist all channels")} · '
            f'loot {_a_tag(loot_bot, "bot")} · {_a_tag(loot_room, "room")}\n'
            "🗝 @aofsubscriptions_bot · /loot · /subscribe · /referral"
        )
        report["lv_urls"] = lv_urls
        report["modifier_id"] = mod.id

        # Deactivate duplicate scrape row with malformed label
        dup = db.query(LootModifier).filter(LootModifier.id == 12).first()
        if dup and execute:
            dup.active = False
            report["deactivated_modifier"] = 12

        captions = _build_captions(lv_urls, footer)
        report["captions"] = captions

        from app.services.loot_pack_pool import (
            build_packs_album_variants,
            configure_packs_promo_pool,
            list_approved_packs_promo_media_ids,
        )

        promo_ids = list_approved_packs_promo_media_ids(db, pool.id)
        album_variants, pool_only = build_packs_album_variants(
            promo_ids,
            len(captions),
            link_slot_offset=len(mods),
        )
        # One row: LV download + Stars deep link (AOF VIP plan id 6 after shop seed).
        buttons = json.dumps(
            [
                [
                    {"text": "⬇ Download Pack", "url": lv_terabox},
                    {
                        "text": "⭐ AOF VIP — 500⭐",
                        "url": "https://t.me/aofsubscriptions_bot?start=c6",
                    },
                ],
                [
                    {"text": "📌 Full stack addlist", "url": addlist_lv},
                    {"text": "🎲 Free pull", "url": loot_bot},
                    {"text": "🏛 Loot Room", "url": loot_room},
                ],
            ]
        )

        sched = (
            db.query(ScheduledTextPost)
            .filter(
                ScheduledTextPost.channel_id == pool.channel_id,
                ScheduledTextPost.name.in_([SCHED_NAME, "AOF PACKS — drop (manual)"]),
            )
            .order_by(ScheduledTextPost.id)
            .first()
        )

        if not sched:
            from app.models.channel import Channel

            ch = db.query(Channel).filter(Channel.identifier == str(AOF_PACKS_CHANNEL_ID)).first()
            if not ch:
                report["error"] = "channel_not_found"
                return report
            sched = ScheduledTextPost(
                name=SCHED_NAME,
                channel_id=ch.id,
                created_at=datetime.now(timezone.utc),
            )
            db.add(sched)
            db.flush()
            report["scheduler_created"] = True

        if execute:
            configure_packs_promo_pool(pool)
            sched.name = SCHED_NAME
            sched.content = captions[0]
            sched.content_variations = json.dumps(captions)
            sched.album_variants_json = json.dumps(album_variants) if album_variants else None
            sched.pool_id = pool.id
            sched.pool_only_mode = pool_only
            sched.pool_randomize = True
            sched.album_size = 1
            sched.buttons = buttons
            sched.checkout_stars_enabled = False
            sched.checkout_stars_plan_id = None
            sched.checkout_button_label = None
            sched.send_silent = False
            sched.pin_after_send = False
            sched.interval_minutes = 480  # 8 variants × ~4h feel; 480 = 8h rotation
            sched.sent_at = None
            sched.caption_rotation_index = 0
            sched.album_order_mode = "static"
            report["scheduler_id"] = sched.id

        if execute:
            db.commit()
    finally:
        db.close()
    return report


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--execute", action="store_true")
    args = p.parse_args()
    r = seed(execute=args.execute)
    print(json.dumps(r, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
