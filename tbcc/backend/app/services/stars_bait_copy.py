"""Stars checkout bait copy — competitor-inspired DM / bot hooks (AOF products only).

Study reference: welcome hook + single CTA → native Telegram Stars subscribe/invoice.
Never impersonate Telegram staff or fake moderation.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.services.aof_growth_hub import resolve_group_access_plan_id


class StarsBaitProduct(str, Enum):
    LOOT_KEY = "loot_key"
    DAY_PASS = "day_pass"
    SUBSCRIPTION = "subscription"


class StarsBaitStyle(str, Enum):
    WELCOME_DIRECT = "welcome_direct"
    SHOCK_CURIOSITY = "shock_curiosity"
    DISCOUNT_SCARCITY = "discount_scarcity"
    CASUAL_NEIGHBOR = "casual_neighbor"
    NATIVE_SUBSCRIBE = "native_subscribe"


@dataclass(frozen=True)
class StarsBaitVariation:
    product: StarsBaitProduct
    style: StarsBaitStyle
    html: str
    button_text: str
    start_payload: str  # payment-bot /start deep link (bait_* → cm*)


def _payment_bot_username() -> str:
    return (
        (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "").strip().lstrip("@")
        or "aofsubscriptions_bot"
    )


def _bot_start_url(payload: str) -> str:
    pay = _payment_bot_username()
    p = (payload or "").strip()
    return f"https://t.me/{pay}?start={p}" if p else f"https://t.me/{pay}"


def resolve_bait_plan_ids(db: Session) -> dict[str, int | None]:
    """Best-effort plan ids for loot key, lane day pass, VIP subscription."""
    from app.models.subscription_plan import SubscriptionPlan

    sub_id = resolve_group_access_plan_id(db)
    loot = (
        db.query(SubscriptionPlan)
        .filter(
            SubscriptionPlan.is_active.is_(True),
            SubscriptionPlan.bot_section == "loot",
            SubscriptionPlan.price_stars > 0,
        )
        .order_by(SubscriptionPlan.price_stars.asc())
        .first()
    )
    lane = (
        db.query(SubscriptionPlan)
        .filter(
            SubscriptionPlan.is_active.is_(True),
            SubscriptionPlan.name.ilike("%lane pass%"),
        )
        .order_by(SubscriptionPlan.id.asc())
        .first()
    )
    if not lane:
        lane = (
            db.query(SubscriptionPlan)
            .filter(
                SubscriptionPlan.is_active.is_(True),
                SubscriptionPlan.bot_section == "loot",
                SubscriptionPlan.duration_days == 1,
                SubscriptionPlan.price_stars > 0,
            )
            .order_by(SubscriptionPlan.price_stars.asc())
            .first()
        )
    return {
        "subscription": int(sub_id) if sub_id else None,
        "loot_key": int(loot.id) if loot else None,
        "day_pass": int(lane.id) if lane else None,
    }


def checkout_start_payload(product: StarsBaitProduct, plan_ids: dict[str, int | None]) -> str:
    """Deep link that lands on Stars checkout (cmN menu or bait handoff)."""
    if product == StarsBaitProduct.LOOT_KEY:
        pid = plan_ids.get("loot_key")
        return f"cm{pid}" if pid else "bait_loot"
    if product == StarsBaitProduct.DAY_PASS:
        pid = plan_ids.get("day_pass")
        return f"cm{pid}" if pid else "bait_day"
    pid = plan_ids.get("subscription")
    return f"cm{pid}" if pid else "bait_vip"


def bait_handoff_payload(product: StarsBaitProduct) -> str:
    return {
        StarsBaitProduct.LOOT_KEY: "bait_loot",
        StarsBaitProduct.DAY_PASS: "bait_day",
        StarsBaitProduct.SUBSCRIPTION: "bait_vip",
    }[product]


_PRODUCT_LABELS = {
    StarsBaitProduct.LOOT_KEY: ("24h Loot Room key", "150", "🗝"),
    StarsBaitProduct.DAY_PASS: ("Lane Pass — 24h", "250", "🎫"),
    StarsBaitProduct.SUBSCRIPTION: ("AOF VIP — 30d", "500", "💎"),
}


def _build_variation(
    product: StarsBaitProduct,
    style: StarsBaitStyle,
    *,
    plan_ids: dict[str, int | None],
) -> StarsBaitVariation:
    label, stars_hint, emoji = _PRODUCT_LABELS[product]
    handoff = bait_handoff_payload(product)
    checkout = checkout_start_payload(product, plan_ids)

    if style == StarsBaitStyle.WELCOME_DIRECT:
        html = (
            f"Welcome. All the {emoji} content is here 👇\n\n"
            f"<i>{label} — tap below. Stars checkout in-app. Cancel anytime.</i>"
        )
        btn = "⭐ Full access ✅"
    elif style == StarsBaitStyle.SHOCK_CURIOSITY:
        html = (
            "Hey. 👋 You need to see what's going on in here — "
            "I'm literally shocked 😳\n\n"
            f"<i>{label} unlocks the private lane. One tap → Telegram Stars.</i>"
        )
        btn = "👉 Visit"
    elif style == StarsBaitStyle.DISCOUNT_SCARCITY:
        html = (
            f"🔥 Limited window — {label.lower()} before the room resets ⌛\n\n"
            f"<i>~{stars_hint}⭐ · exclusive drops you won't find on the public feed.</i>"
        )
        btn = "📹 Grab deal"
    elif style == StarsBaitStyle.CASUAL_NEIGHBOR:
        html = (
            "thought you'd want first look before the feed gets noisy.\n\n"
            f"<b>{label}</b> — same stack, wrapped lanes, bigger pulls."
        )
        btn = "🔓 Let me in"
    else:  # NATIVE_SUBSCRIBE
        html = (
            f"Subscribe to <b>{label}</b> for <b>{stars_hint} ⭐</b>?\n\n"
            "<i>By continuing you get instant access — not a fake mod message, "
            "just the real AOF checkout.</i>"
        )
        btn = f"⭐ {stars_hint} Stars — Subscribe"

    return StarsBaitVariation(
        product=product,
        style=style,
        html=html,
        button_text=btn[:64],
        start_payload=handoff if style != StarsBaitStyle.NATIVE_SUBSCRIBE else checkout,
    )


def all_stars_bait_variations(plan_ids: dict[str, int | None] | None = None) -> list[StarsBaitVariation]:
    """Full matrix: 3 products × 5 styles."""
    pids = plan_ids or {}
    out: list[StarsBaitVariation] = []
    for product in StarsBaitProduct:
        for style in StarsBaitStyle:
            out.append(_build_variation(product, style, plan_ids=pids))
    return out


def pick_stars_bait_variation(
    db: Session,
    *,
    product: StarsBaitProduct | None = None,
    style: StarsBaitStyle | None = None,
    seed: int | None = None,
) -> StarsBaitVariation:
    plan_ids = resolve_bait_plan_ids(db)
    pool = all_stars_bait_variations(plan_ids)
    if product:
        pool = [v for v in pool if v.product == product]
    if style:
        pool = [v for v in pool if v.style == style]
    if not pool:
        pool = all_stars_bait_variations(plan_ids)
    if seed is not None:
        return pool[seed % len(pool)]
    return random.choice(pool)


def stars_bait_inline_keyboard(variation: StarsBaitVariation) -> dict[str, Any]:
    url = _bot_start_url(variation.start_payload)
    return {"inline_keyboard": [[{"text": variation.button_text, "url": url}]]}


def stars_bait_channel_captions(db: Session) -> list[str]:
    """Short channel pacing lines → payment bot bait handoff."""
    plan_ids = resolve_bait_plan_ids(db)
    lines: list[str] = []
    for v in all_stars_bait_variations(plan_ids):
        pay = _payment_bot_username()
        lines.append(
            f"{v.html}\n\n"
            f'→ <a href="https://t.me/{pay}?start={v.start_payload}">{v.button_text}</a>'
        )
    return lines


def stars_bait_welcome_enabled() -> bool:
    raw = (os.getenv("TBCC_STARS_BAIT_WELCOME") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def parse_bait_start_payload(payload: str) -> StarsBaitProduct | None:
    p = (payload or "").strip().lower()
    if p in ("bait_loot", "loot_bait"):
        return StarsBaitProduct.LOOT_KEY
    if p in ("bait_day", "day_bait", "bait_pass"):
        return StarsBaitProduct.DAY_PASS
    if p in ("bait_vip", "bait_sub", "bait_subscription"):
        return StarsBaitProduct.SUBSCRIPTION
    if p == "bait":
        return random.choice(list(StarsBaitProduct))
    return None
