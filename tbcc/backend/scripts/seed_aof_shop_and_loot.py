"""
Seed subscription plans (loot 24h keys + basic main), loot pools, modifiers after DB wipe.

  cd tbcc/backend && py -3.13 scripts/seed_aof_shop_and_loot.py
  py -3.13 scripts/seed_aof_shop_and_loot.py --execute
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.models.content_pool import ContentPool
from app.models.loot import LootModifier, LootIntervalTier
from app.models.subscription_plan import SubscriptionPlan
from app.services.linkvertise_wrap import publisher_id_from_env, wrap_linkvertise_url
from app.services.loot_pool_eligibility_seed import (
    seed_content_pool_loot_eligibility,
    seed_loot_room_pool_eligibility,
)

STARS_USD = float(os.getenv("TBCC_STARS_USD_PER_STAR") or "0.012")
LOOT_GROUP_CHANNEL_ID = 8  # LOOT ROOM GROUP
MAIN_HUB_CHANNEL_ID = 1

LOOT_PLANS = [
    ("m60", "Loot Room 24h — 60min drops", 150, "Standard pace: one drop per hour for 24 hours."),
    ("m45", "Loot Room 24h — 45min drops", 220, "Faster cadence: drops every 45 minutes."),
    ("m30", "Loot Room 24h — 30min drops", 320, "Hot pace + 1 bonus album draw per session."),
    ("m15", "Loot Room 24h — 15min drops", 480, "Max pace + 2 bonus draws + rarity shift."),
]

LOOT_POOL_NAMES = [
    "LOOT ROOM FLOOR — AOF AI",
    "LOOT ROOM FLOOR — AOF ASS",
    "LOOT ROOM FLOOR — AOF BIG TITS",
    "LOOT ROOM FLOOR — AOF BLOWJOB",
    "LOOT ROOM FLOOR — AOF MILF",
    "LOOT ROOM FLOOR — AOF TABOO",
    "LOOT ROOM SPOTLIGHT — VOYEUR",
    "LOOT ROOM SPOTLIGHT — ABG",
    "LOOT ROOM VAULT — MAIN",
    "LOOT ROOM VAULT — LOOT CHANNEL",
]

CHANNEL_INVITES = [
    ("AOF Main Hub", "https://t.me/+hMQzGsBFjF02MDkx", "telegram_group", 1),
    ("AOF AI", "https://t.me/+4umB83be5n41MmEx", "telegram_channel", 5),
    ("AOF ASS", "https://t.me/+gQaguoQE7eM4MzA5", "telegram_channel", 5),
    ("AOF BIG TITS", "https://t.me/+vPhWRgtpteI4NTdh", "telegram_channel", 5),
    ("AOF BLOWJOB", "https://t.me/+3jeQNQhcOSU4ZTcx", "telegram_channel", 5),
    ("AOF MILF", "https://t.me/+AY0zGwyeAy9jNDIx", "telegram_channel", 5),
    ("AOF TABOO", "https://t.me/+w46b7uJK5eo0MDcx", "telegram_channel", 6),
    ("AOF PUBLIC VOYEUR", "https://t.me/+ag3BSf3fliwyYTgx", "telegram_channel", 6),
    ("AOF LOOT ROOM", "https://t.me/+NWathiLSqZ1lMzlh", "telegram_group", 4),
    ("AOF Addlist", "https://t.me/addlist/r-7_7CGIkExhMDcx", "telegram_group", 3),
]


def _usd(stars: int) -> float:
    return round(stars * STARS_USD, 2)


def _lv(url: str, pub: str) -> str:
    return wrap_linkvertise_url(pub, url)


def seed(execute: bool) -> dict:
    pub = publisher_id_from_env()
    loot_invite = (os.getenv("TBCC_LOOT_ROOM_INVITE_URL") or "https://t.me/+97f4Crv3G1RkMGU5").strip()
    report: dict = {"plans": [], "pools": [], "modifiers": [], "eligibility": []}

    db = SessionLocal()
    try:
        existing_plans = db.query(SubscriptionPlan).count()
        if existing_plans == 0:
            for code, name, stars, blurb in LOOT_PLANS:
                desc = (
                    f"{blurb}\n\n24-hour private Loot Room access. "
                    f"Join: {loot_invite}\nRolls via @aof_lootgod_bot\nInterval code: {code}"
                )
                report["plans"].append({"name": name, "stars": stars, "section": "loot"})
                if execute:
                    db.add(
                        SubscriptionPlan(
                            name=name,
                            price_stars=stars,
                            duration_days=1,
                            channel_id=LOOT_GROUP_CHANNEL_ID,
                            description=desc,
                            description_variations_json=json.dumps(
                                [
                                    f"24h key · {code} · spoiler drops in DM",
                                    "Full modifier table — zips & gated links on tier 5+",
                                ]
                            ),
                            is_active=True,
                            product_type="subscription",
                            bot_section="loot",
                            nowpayments_price_usd=_usd(stars),
                            nowpayments_allow_any_currency=True,
                            nowpayments_pay_currency=(
                                os.getenv("TBCC_NOWPAYMENTS_PAY_CURRENCY") or "usdttrc20"
                            ),
                        )
                    )
            # One main community sub
            report["plans"].append({"name": "AOF Main — 30 days", "stars": 500, "section": "main"})
            if execute:
                db.add(
                    SubscriptionPlan(
                        name="AOF Main — 30 days",
                        price_stars=500,
                        duration_days=30,
                        channel_id=MAIN_HUB_CHANNEL_ID,
                        description="30-day access to the AOF main community hub.",
                        is_active=True,
                        product_type="subscription",
                        bot_section="main",
                        nowpayments_price_usd=_usd(500),
                        nowpayments_allow_any_currency=True,
                    )
                )

        pool_count = db.query(ContentPool).filter(ContentPool.name.like("LOOT ROOM%")).count()
        if pool_count < len(LOOT_POOL_NAMES):
            for pname in LOOT_POOL_NAMES:
                if db.query(ContentPool).filter(ContentPool.name == pname).first():
                    continue
                report["pools"].append(pname)
                if execute:
                    ch = LOOT_GROUP_CHANNEL_ID if "LOOT" in pname else MAIN_HUB_CHANNEL_ID
                    db.add(
                        ContentPool(
                            name=pname,
                            channel_id=ch,
                            album_size=5,
                            interval_minutes=0,
                            auto_post_enabled=False,
                            randomize_queue=True,
                        )
                    )

        if execute:
            db.flush()

        mod_count = db.query(LootModifier).count()
        if mod_count == 0:
            for label, url, kind, min_tier in CHANNEL_INVITES:
                lv_url = _lv(url, pub)
                report["modifiers"].append({"label": label, "url": lv_url[:80]})
                if execute:
                    db.add(
                        LootModifier(
                            kind=kind,
                            label=label,
                            target_url=lv_url,
                            weight_base=1.0,
                            rarity_focus=1.2,
                            min_rarity_tier=min_tier,
                            active=True,
                            source_note=f"seed_aof_shop_and_loot; original={url}",
                        )
                    )

        if execute:
            db.commit()
            report["eligibility"] = seed_loot_room_pool_eligibility(db)
            report["content_pool_eligibility"] = seed_content_pool_loot_eligibility(db)
        else:
            tiers = db.query(LootIntervalTier).count()
            report["loot_interval_tiers"] = tiers
            from app.services.loot_pool_eligibility_seed import tier_coverage_report

            report["tier_coverage"] = tier_coverage_report(db)
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
