#!/usr/bin/env python3
"""Seed promo_affiliate_links with Musebox + core AOF sponsors + AI tool affiliates (idempotent by URL)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.models.promo_affiliate_link import PromoAffiliateLink

SEED_ITEMS: list[dict] = [
    {
        "label": "Musebox AI",
        "url": "https://musebox.ai/?ref=uOg77ImI",
        "payout_kind": "revshare",
        "priority_tier": 4,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🎨 {link} — AI creative playground",
    },
    {
        "label": "Undress AI bot",
        "url": "https://nodress.site/tg/bot?username=Aifasteditbot&ref_id=7787282561",
        "payout_kind": "revshare",
        "priority_tier": 3,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": [],
        "copy_template": "💰 {link} — free credits",
    },
    {
        "label": "DrawAI",
        "url": "https://t.me/drawai_0_bot?start=7787282561",
        "payout_kind": "revshare",
        "priority_tier": 5,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🎬 {link} — photo to motion",
    },
    {
        "label": "BotyNude",
        "url": "https://botynude.com/ref/39Z9HHK3",
        "payout_kind": "revshare",
        "priority_tier": 6,
        "placements": ["x_buffer", "telegram_footer", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "💰 {link} — 2 free coins per join",
    },
    {
        "label": "MotionMuse",
        "url": "https://motionmuse.ai/r/wi9rtg3l",
        "payout_kind": "revshare",
        "priority_tier": 7,
        "placements": ["x_buffer", "telegram_footer", "loot_roll"],
        "network_keys": ["ai"],
        "copy_template": "🎬 {link} — invite friends, earn credits",
    },
    {
        "label": "BangBros PPS",
        "url": "https://landing.bangbrosnetwork.com/?ats=eyJhIjoxMTUwNDY3LCJjIjo2MzE0NzY4MCwibiI6MTMwLCJzIjo2OTMsImUiOjEwNjczLCJwIjoxMX0=",
        "payout_kind": "pps",
        "priority_tier": 8,
        "placements": ["x_buffer", "telegram_footer", "loot_roll"],
        "network_keys": ["milf", "taboo", "big_tits"],
        "copy_template": "🔞 {link}",
    },
    {
        "label": "Reality Kings PPS",
        "url": "https://landing.rk.com/tgp1/?ats=eyJhIjoxMTUwNDY3LCJjIjo2MzE0NzY4MCwibiI6MjAsInMiOjM1OCwiZSI6ODAzNCwicCI6MTF9",
        "payout_kind": "pps",
        "priority_tier": 9,
        "placements": ["x_buffer"],
        "network_keys": ["milf", "voyeur"],
        "copy_template": "🔞 {link}",
    },
    {
        "label": "Spicevids PPS",
        "url": "https://landing.spicevids.com/affiliates/?ats=eyJhIjoxMTUwNDY3LCJjIjo2MzE0NzY4MCwibiI6MTIwLCJzIjo2ODAsImUiOjEwNDMyLCJwIjoxMX0=",
        "payout_kind": "pps",
        "priority_tier": 10,
        "placements": ["telegram_footer", "loot_roll"],
        "network_keys": ["goon", "bop"],
        "copy_template": "🔞 {link}",
    },
    {
        "label": "Nutaku — Lust Goddess",
        "url": "https://network.nutaku.net/images/lp/lust-goddess/video/1/?ats=eyJhIjoxMTUwNDY3LCJjIjo2MzE0NzY4MCwibiI6MSwicyI6MSwiZSI6MTA5MDMsInAiOjJ9",
        "payout_kind": "cpa",
        "priority_tier": 11,
        "placements": ["x_buffer", "links_hub"],
        "network_keys": [],
        "copy_template": "🎮 {link}",
    },
    # --- Infrastructure / ops (links_hub PARTNERS lane — not links_hub_ai) ---
    {
        "label": "Pulsed Media seedbox",
        "url": "https://pulsedmedia.com/clients/aff.php?aff=10812",
        "payout_kind": "other",
        "priority_tier": 45,
        "placements": ["manual_only", "links_hub"],
        "network_keys": [],
        "copy_template": "📦 {link} — remote storage & fast cloud transfers",
    },
    {
        "label": "Cursor referral",
        "url": "https://cursor.com/referral?code=WKMSQ8BYPM1O",
        "payout_kind": "other",
        "priority_tier": 50,
        "placements": ["manual_only"],
        "network_keys": [],
        "copy_template": "🛠 {link}",
    },
    {
        "label": "Claude referral",
        "url": "https://claude.ai/referral/ve9d3Ki_QA",
        "payout_kind": "other",
        "priority_tier": 51,
        "placements": ["manual_only"],
        "network_keys": [],
        "copy_template": "🛠 {link}",
    },
    # --- AI tools lane (retention / bot directory) ---
    {
        "label": "Nakedly (nudify.now)",
        "url": "https://nudify.now/?code=U214D",
        "payout_kind": "revshare",
        "priority_tier": 5,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🧠 {link} — AI tools hub (revshare on purchases)",
    },
    {
        "label": "Playbun",
        "url": "https://www.playbun.com/?ref=freeusegod",
        "payout_kind": "revshare",
        "priority_tier": 13,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🎬 {link} — NSFW AI video",
    },
    {
        "label": "Vixal — image to video",
        "url": "https://vixal.to/i2v/7787282561",
        "payout_kind": "revshare",
        "priority_tier": 14,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🎬 {link} — still → motion (115k/mo)",
    },
    {
        "label": "Lucid Dreams Bot",
        "url": "https://t.me/luciddreams?start=_tgr_vYQc3UQzM2Qx",
        "payout_kind": "revshare",
        "priority_tier": 12,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": [],
        "copy_template": "💭 {link} — your AI girlfriend",
    },
    {
        "label": "Perfecto 69 Bot",
        "url": "https://t.me/Perfecto_69_Bot?start=_tgr_5NKS5UYwOGMx",
        "payout_kind": "revshare",
        "priority_tier": 12,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "✨ {link} — AI companion bot",
    },
    {
        "label": "Hot Dreams Bot",
        "url": "https://hotdreamsai.com/?start=7787282561",
        "payout_kind": "revshare",
        "priority_tier": 15,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": [],
        "copy_template": "✨ {link} — photo/video dream engine",
    },
    {
        "label": "Video Generator bot",
        "url": "https://t.me/image2videos6919bot?start=7787282561",
        "payout_kind": "revshare",
        "priority_tier": 16,
        "placements": ["telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🎬 {link} — image2video TG bot",
    },
    {
        "label": "DeleteMyPanties Bot",
        "url": "https://braundress.me/entry?start=eNCA01Du",
        "payout_kind": "revshare",
        "priority_tier": 17,
        "placements": ["telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🧠 {link} — undress TG bot",
    },
    {
        "label": "Fapify",
        "url": "https://www.fapify.com/?ref=freeusegod",
        "payout_kind": "revshare",
        "priority_tier": 18,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🎨 {link} — AI generator suite",
    },
    {
        "label": "AI Bot Gateway",
        "url": "https://botsgates-html.vercel.app/?b=img2vid&r=7787282561",
        "payout_kind": "revshare",
        "priority_tier": 19,
        "placements": ["telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🤖 {link} — img2vid / img2img gateway",
    },
    {
        "label": "Satisfactory (Randi123)",
        "url": "https://satisfactory.studio/r/ref_7787282561",
        "payout_kind": "revshare",
        "priority_tier": 20,
        "placements": ["x_buffer", "telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🤖 {link} — TG bot",
    },
    {
        "label": "Sweet Sdx (Veners)",
        "url": "https://venersbot.com/7787282561",
        "payout_kind": "revshare",
        "priority_tier": 21,
        "placements": ["telegram_footer", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "💋 {link} — TG bot",
    },
    {
        "label": "HeatMe",
        "url": "https://heatme.ai/r/wrzw79feke",
        "payout_kind": "revshare",
        "priority_tier": 22,
        "placements": ["telegram_footer", "links_hub_ai", "loot_roll"],
        "network_keys": ["ai", "main"],
        "copy_template": "🔥 {link} — invite credits",
    },
]


def _encode_list(values: list[str]) -> str | None:
    cleaned = [v.strip().lower() for v in values if v and str(v).strip()]
    return json.dumps(cleaned) if cleaned else None


def _ensure_tables() -> None:
    from sqlalchemy import inspect

    from app.database.session import engine
    from app.models.base import Base
    from app.models.promo_affiliate_link import PromoAffiliateLink  # noqa: F401
    from app.models.promo_affiliate_rotation_cursor import PromoAffiliateRotationCursor  # noqa: F401

    inspector = inspect(engine)
    names = set(inspector.get_table_names())
    if "promo_affiliate_links" not in names or "promo_affiliate_rotation_cursors" not in names:
        Base.metadata.create_all(
            bind=engine,
            tables=[
                PromoAffiliateLink.__table__,
                PromoAffiliateRotationCursor.__table__,
            ],
        )


def main() -> None:
    _ensure_tables()
    db = SessionLocal()
    created = 0
    updated = 0
    try:
        for item in SEED_ITEMS:
            url = str(item["url"]).strip()
            label = str(item["label"]).strip()
            row = db.query(PromoAffiliateLink).filter(PromoAffiliateLink.url == url).first()
            if not row:
                row = (
                    db.query(PromoAffiliateLink)
                    .filter(PromoAffiliateLink.label == label)
                    .first()
                )
            if not row:
                row = PromoAffiliateLink(label=label, url=url)
                db.add(row)
                created += 1
            else:
                updated += 1
            row.url = url
            row.label = str(item["label"])[:512]
            row.payout_kind = str(item.get("payout_kind") or "other")[:16]
            row.priority_tier = int(item.get("priority_tier") or 10)
            row.active = True
            row.placements_json = _encode_list(list(item.get("placements") or ["manual_only"]))
            row.network_keys_json = _encode_list(list(item.get("network_keys") or []))
            row.copy_template = str(item.get("copy_template") or "")[:1024] or None
        db.commit()
        print(f"Seed complete: created={created} updated={updated} total={len(SEED_ITEMS)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
