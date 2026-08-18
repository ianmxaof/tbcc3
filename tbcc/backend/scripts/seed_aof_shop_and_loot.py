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
from app.data.aof_vip_membership import (
    VIP_INTRO_PLAN_NAME,
    VIP_INTRO_PRICE_CENTS,
    VIP_INTRO_SKU,
    VIP_MEMBERSHIP_SKUS,
    protected_main_vip_plan_names,
    vip_display_name,
    vip_intro_period_label,
)
from app.data.aof_network import AOF_VIP_IDENT
from app.data.loot_lane_economy import LANE_PASS_SKU, MONTHLY_MEGA, PACK_DROP, usd_to_stars
from app.models.channel import Channel
from app.services.aof_vip_fulfillment import vip_channel_ident

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
    ("AOF LOOT ROOM", "https://t.me/+97f4Crv3G1RkMGU5", "telegram_group", 4),
    ("AOF Addlist", "https://t.me/addlist/r-7_7CGIkExhMDcx", "telegram_group", 3),
]


def _usd(stars: int) -> float:
    return round(stars * STARS_USD, 2)


def _lv(url: str, pub: str) -> str:
    return wrap_linkvertise_url(pub, url)


def _ensure_plan(
    db,
    *,
    execute: bool,
    report: dict,
    name: str,
    stars: int,
    usd: float,
    duration_days: int,
    product_type: str,
    bot_section: str,
    description: str,
    channel_id: int | None,
    variations: list[str] | None = None,
) -> None:
    existing = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == name).first()
    if existing:
        report["plans"].append({"name": name, "stars": stars, "section": bot_section, "status": "exists"})
        return
    report["plans"].append({"name": name, "stars": stars, "section": bot_section, "status": "create"})
    if not execute:
        return
    db.add(
        SubscriptionPlan(
            name=name,
            price_stars=stars,
            duration_days=duration_days,
            channel_id=channel_id,
            description=description,
            description_variations_json=json.dumps(variations or []),
            is_active=True,
            product_type=product_type,
            bot_section=bot_section,
            nowpayments_price_usd=usd,
            nowpayments_allow_any_currency=True,
            nowpayments_pay_currency=(os.getenv("TBCC_NOWPAYMENTS_PAY_CURRENCY") or "usdttrc20"),
        )
    )


def _vip_channel_db_id(db) -> int | None:
    ident = vip_channel_ident() or AOF_VIP_IDENT
    row = db.query(Channel).filter(Channel.identifier == str(ident)).first()
    if row:
        return int(row.id)
    return None


def seed_vip_membership_skus(db, *, execute: bool, report: dict) -> None:
    """Idempotent: five AOF VIP terms matching Gumroad ynnulc (Stars + NOWPayments USD)."""
    vip_ch = _vip_channel_db_id(db)
    channel_id = vip_ch if vip_ch is not None else MAIN_HUB_CHANNEL_ID
    tier = vip_display_name()
    vip_names = frozenset(sku.name for sku in VIP_MEMBERSHIP_SKUS)
    for sku in VIP_MEMBERSHIP_SKUS:
        stars = usd_to_stars(sku.price_usd, stars_per_usd=STARS_USD)
        existing = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == sku.name).first()
        desc = (
            f"{sku.blurb}\n"
            f"${sku.price_usd:.0f} / {sku.duration_days}d · {stars}⭐\n"
            f"Card: same {tier} term via card / USD checkout. Crypto: NOWPayments.\n"
            f"Fulfillment: @aofsubscriptions_bot → {tier} invite DM."
        )
        if existing:
            report["plans"].append(
                {
                    "name": sku.name,
                    "stars": stars,
                    "usd": sku.price_usd,
                    "section": "main",
                    "status": "update" if execute else "exists",
                    "recurrence": sku.gumroad_recurrence,
                }
            )
            if execute:
                existing.price_stars = stars
                existing.duration_days = sku.duration_days
                existing.nowpayments_price_usd = sku.price_usd
                existing.nowpayments_allow_any_currency = True
                existing.is_active = True
                existing.product_type = "subscription"
                existing.bot_section = "main"
                existing.description = desc
                existing.channel_id = channel_id
            continue
        _ensure_plan(
            db,
            execute=execute,
            report=report,
            name=sku.name,
            stars=stars,
            usd=sku.price_usd,
            duration_days=sku.duration_days,
            product_type="subscription",
            bot_section="main",
            channel_id=channel_id,
            description=desc,
            variations=[
                f"{tier} {sku.gumroad_recurrence} · ${sku.price_usd:.0f}",
                "All lanes · loot priority · Telegram delivery",
            ],
        )


def seed_vip_intro_month(db, *, execute: bool, report: dict) -> None:
    """Idempotent: one-time intro price for first-time main-section buyers."""
    from app.services.vip_intro_eligibility import vip_intro_usd

    sku = VIP_INTRO_SKU
    usd = vip_intro_usd()
    stars = usd_to_stars(usd, stars_per_usd=STARS_USD)
    vip_ch = _vip_channel_db_id(db)
    channel_id = vip_ch if vip_ch is not None else MAIN_HUB_CHANNEL_ID
    tier = vip_display_name()
    period = vip_intro_period_label()
    desc = (
        f"{sku.blurb}\n"
        f"${usd:.0f} / {sku.duration_days}d · {stars}⭐ · <b>first {tier} purchase only</b>\n"
        f"Same perks as standard {tier}. Renews at standard rates after {sku.duration_days} days.\n"
        f"Card / crypto / Stars via @aofsubscriptions_bot → {tier} invite DM."
    )
    existing = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == VIP_INTRO_PLAN_NAME).first()
    if existing:
        report["plans"].append(
            {
                "name": VIP_INTRO_PLAN_NAME,
                "stars": stars,
                "usd": usd,
                "section": "main",
                "status": "update" if execute else "exists",
                "intro": True,
            }
        )
        if execute:
            existing.price_stars = stars
            existing.duration_days = sku.duration_days
            existing.nowpayments_price_usd = usd
            existing.nowpayments_allow_any_currency = True
            existing.is_active = True
            existing.product_type = "subscription"
            existing.bot_section = "main"
            existing.description = desc
            existing.channel_id = channel_id
        return
    _ensure_plan(
        db,
        execute=execute,
        report=report,
        name=VIP_INTRO_PLAN_NAME,
        stars=stars,
        usd=usd,
        duration_days=sku.duration_days,
        product_type="subscription",
        bot_section="main",
        channel_id=channel_id,
        description=desc,
        variations=[
            f"Intro {tier} · ${usd:.0f} first {period}",
            f"First-time {tier} only · renews at standard rates",
        ],
    )


def deactivate_legacy_main_vip_plans(db, *, execute: bool, report: dict) -> None:
    """Retire duplicate monthly-only main rows so /subscribe shows the VIP ladder only."""
    protected = protected_main_vip_plan_names()
    rows = (
        db.query(SubscriptionPlan)
        .filter(
            SubscriptionPlan.bot_section == "main",
            SubscriptionPlan.product_type == "subscription",
            SubscriptionPlan.is_active.is_(True),
        )
        .all()
    )
    for row in rows:
        if (row.name or "") in protected:
            continue
        low = (row.name or "").lower()
        if not any(tok in low for tok in ("main", "vip", "premium", "group access", "aof main")):
            continue
        report["plans"].append({"name": row.name, "status": "deactivated_legacy", "id": row.id})
        if execute:
            row.is_active = False


def build_gumroad_product_map(db) -> dict[str, int]:
    """JSON-ready map for TBCC_GUMROAD_PRODUCT_MAP (permalink + price cents → plan_id)."""
    from app.data.aof_vip_membership import (
        VIP_INTRO_PLAN_NAME,
        VIP_INTRO_PRICE_CENTS,
        VIP_MEMBERSHIP_SKUS,
        VIP_PRICE_CENTS_TO_RECURRENCE,
        sku_for_recurrence,
    )

    out: dict[str, int] = {}
    recurrence_to_pid: dict[str, int] = {}
    for sku in VIP_MEMBERSHIP_SKUS:
        row = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == sku.name).first()
        if not row or not row.is_active:
            continue
        pid = int(row.id)
        recurrence_to_pid[sku.gumroad_recurrence] = pid
        cents = int(round(float(sku.price_usd) * 100))
        out[f"price:{cents}"] = pid

    intro_row = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == VIP_INTRO_PLAN_NAME).first()
    if intro_row and intro_row.is_active:
        out[f"price:{VIP_INTRO_PRICE_CENTS}"] = int(intro_row.id)

    # Legacy + current Gumroad ping price cents → plan id (grandfathered renewals)
    for cents, recurrence in VIP_PRICE_CENTS_TO_RECURRENCE.items():
        pid = recurrence_to_pid.get(recurrence)
        if pid is not None:
            out[f"price:{int(cents)}"] = pid

    monthly_id = recurrence_to_pid.get("monthly")
    if monthly_id is not None:
        out["ynnulc"] = monthly_id
    return out


def seed_lane_economy_skus(db, *, execute: bool, report: dict) -> None:
    """Idempotent: Lane Pass $3 + Curated Pack + Monthly MEGA PACK shop rows."""
    loot_invite = (os.getenv("TBCC_LOOT_ROOM_INVITE_URL") or "https://t.me/+97f4Crv3G1RkMGU5").strip()
    pass_stars = usd_to_stars(LANE_PASS_SKU.price_usd, stars_per_usd=STARS_USD)
    curated_stars = usd_to_stars(PACK_DROP.price_usd, stars_per_usd=STARS_USD)
    mega_stars = usd_to_stars(MONTHLY_MEGA.price_usd, stars_per_usd=STARS_USD)

    _ensure_plan(
        db,
        execute=execute,
        report=report,
        name=LANE_PASS_SKU.sku_name,
        stars=pass_stars,
        usd=LANE_PASS_SKU.price_usd,
        duration_days=LANE_PASS_SKU.duration_days,
        product_type="subscription",
        bot_section=LANE_PASS_SKU.bot_section,
        channel_id=LOOT_GROUP_CHANNEL_ID,
        description=(
            f"${LANE_PASS_SKU.price_usd:.0f} Lane Pass — 24h access to one AOF lane channel "
            f"(protected, light watermark) + Loot God roll perks.\n"
            f"Hub: {loot_invite}\n"
            "Full set after Glimpse · not clean forwards."
        ),
        variations=[
            "Lane Pass $3 · 24h · one door · roll perks",
            "Protected channel access — members-only vault",
        ],
    )
    _ensure_plan(
        db,
        execute=execute,
        report=report,
        name=PACK_DROP.sku_name,
        stars=curated_stars,
        usd=PACK_DROP.price_usd,
        duration_days=0,
        product_type="bundle",
        bot_section="packs",
        channel_id=None,
        description=(
            f"Operator-curated pack (~{PACK_DROP.soft_min_items}–{PACK_DROP.soft_max_items} items). "
            "Theme-led, not a scrape dump. Includes a Loot Flair modifier roll after purchase. "
            "Zip fulfillment attached when ready."
        ),
        variations=[
            "Curated Pack — theme-led seal + Loot Flair",
            "Members-only vault · one gate per purchase",
        ],
    )
    _ensure_plan(
        db,
        execute=execute,
        report=report,
        name=MONTHLY_MEGA.sku_name,
        stars=mega_stars,
        usd=MONTHLY_MEGA.price_usd,
        duration_days=0,
        product_type="bundle",
        bot_section="packs",
        channel_id=None,
        description=(
            "Monthly MEGA PACK — wrap of this month's curated packs into one seal. "
            "Best one-shot odds / Loot Flair. Zip when month closes."
        ),
        variations=[
            "Monthly MEGA — all curated packs this month",
            "Premium vault dump · Loot Flair included",
        ],
    )


def seed(execute: bool) -> dict:
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

        # Lane economy + VIP ladder — always idempotent (even when other plans already exist)
        seed_lane_economy_skus(db, execute=execute, report=report)
        seed_vip_membership_skus(db, execute=execute, report=report)
        seed_vip_intro_month(db, execute=execute, report=report)
        deactivate_legacy_main_vip_plans(db, execute=execute, report=report)
        if execute:
            db.flush()
            report["gumroad_product_map"] = build_gumroad_product_map(db)

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
            pub = publisher_id_from_env()
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
            from app.data.telegram_stars_howto import ensure_stars_howto_caption_snippet

            report["stars_howto_snippet"] = ensure_stars_howto_caption_snippet(db)
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
