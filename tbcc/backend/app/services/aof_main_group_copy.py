"""Minimal PACKS-style copy for AOF main group — dense, hyperlinked, depraved edge."""

from __future__ import annotations

import html
import os
from typing import Any

from sqlalchemy.orm import Session


def _a(url: str, label: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def _bot() -> str:
    return (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "aofsubscriptions_bot").strip().lstrip("@")


def minimal_checkout_caption_html(
    db: Session,
    plan_id: int,
    *,
    stars: int | None = None,
    days: int = 30,
) -> str:
    """One dense paragraph for Pay ⭐ bot follow-up — no bullet walls."""
    from app.data.aof_vip_membership import vip_display_name
    from app.models.subscription_plan import SubscriptionPlan
    from app.services.aof_growth_hub import resolve_group_access_plan_id

    pid = int(plan_id or resolve_group_access_plan_id(db))
    if stars is None:
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == pid).first()
        stars = int(plan.price_stars or 0) if plan else 0
        days = int(plan.duration_days or 30) if plan else 30
    bot = _bot()
    tier = vip_display_name()
    price = f"<b>{stars}⭐</b>/{days}d · " if stars > 0 else ""
    return (
        f"🎫 <b>AOF {tier}</b> — {price}skip the gates, daily god roll, weekly mega dump, "
        f"@{bot} credits. Unwrapped lanes, bigger drops, {tier}-only perks — public stays on the wrapped feed. "
        f"<i>Tap Pay ⭐ — instant access.</i>"
    )


def heartbeat_variations(lv: dict[str, str], checkout_line: str) -> list[str]:
    """Short pulse lines for main-group heartbeat rotation."""
    addlist = _a(lv.get("addlist", ""), "addlist")
    hub = _a(lv.get("mainhub", "https://telegram.me/aofmainhub"), "hub")
    bot = _bot()
    return [
        (
            f"🔥 <b>AOF MAIN</b> — TBCC pipeline feeding the network. "
            f"LOOT keys · premium lanes · {addlist} · {hub} · @{bot}"
            f"{checkout_line}"
        ),
        (
            f"⚡ Fresh lane drop — scroll or miss it. "
            f"VIP gets unwrapped hosts + daily /viproll — @{bot} /subscribe"
            f"{checkout_line}"
        ),
        (
            f"🔞 Another deposit cleared QA — porn first, paragraphs never. "
            f"Stack lives at {addlist} · Pay ⭐ skips the circus"
            f"{checkout_line}"
        ),
        (
            f"💀 You weren't invited. You stayed anyway. "
            f"Gates filter tourists — {hub} · @{bot} · /loot · /referral"
            f"{checkout_line}"
        ),
    ]


def drop_ticker_variations() -> list[str]:
    return [
        "📦 Pipeline drop — another batch hit a lane. Scroll or cope.",
        "🌀 Relay fired — storage → pool → your feed. Conveyor doesn't sleep.",
        "⚡ GOON · BOP · TABOO lanes eating deposits this week — stay glued.",
        "🔔 Thin lane pulse — next rotation lands before you finish typing.",
    ]


def spotlight_variation(lane_name: str, lane_url: str, checkout_line: str) -> str:
    name = html.escape(lane_name.strip() or "lane")
    link = _a(lane_url, lane_name.strip() or "lane")
    from app.services.aof_feed_rhythm_v2 import main_group_album_size, vip_album_roll_max, vip_album_roll_min

    pub = main_group_album_size()
    lo, hi = vip_album_roll_min(), vip_album_roll_max()
    return (
        f"👀 <b>{name}</b> rotating now — {link}. "
        f"Tease album: {pub} here · VIP rolls <b>{lo}–{hi}</b> early, no wrap torture. Pay ⭐ below"
        f"{checkout_line}"
    )


def vip_promo_minimal_bodies() -> list[str]:
    bot = _bot()
    return [
        (
            f"🔓 <b>Skip the gates</b> — VIP is the silo for people who hate ads more than they hate paying. "
            f"Tap Pay ⭐ · @{bot}"
        ),
        (
            f"🎰 <b>Daily god roll</b> + weekly mega + rolled albums (3–10) — VIP only. "
            f"Public gets the wrapped tease. @{bot} /subscribe"
        ),
        (
            f"💎 Public = wrapped · slow · scattered. VIP = direct hosts, bigger albums, @{bot} credits. "
            f"Pay ⭐ below."
        ),
    ]


def gate_fomo_minimal_bodies() -> list[str]:
    return [
        "🔗 Gate ritual: tap link → Complete Actions → Get Link. 30 seconds, then the folder.",
        "📎 Wrapped = one ad between you and the file. Finish the step or stay thirsty.",
    ]


def feed_rhythm_interjection_body(lane_name: str, footer: str) -> str:
    return (
        f"🔥 <b>{html.escape(lane_name)}</b> — curated lane break. "
        f"Media > your unread promo essays. VIP skips ads."
        f"{footer}"
    )


def main_group_promo_html() -> str:
    bot = _bot()
    return (
        f"🔥 <b>AOF MAIN</b> — hub that feeds the network. "
        f"TBCC pipeline · LOOT keys · premium lanes — @{bot} · /loot · /referral"
    )


def aof_copy_llm_enabled() -> bool:
    return (os.getenv("TBCC_AOF_COPY_LLM_ENABLED") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def aof_copy_llm_model() -> str:
    return (
        os.getenv("TBCC_AOF_COPY_LLM_MODEL")
        or os.getenv("TBCC_LLM_CHAT_OPENROUTER_MODEL")
        or os.getenv("TBCC_OPENROUTER_MODEL")
        or "cognitivecomputations/dolphin-mistral-24b-venice-edition:free"
    ).strip()


def maybe_llm_sharpen_copy(text: str) -> str:
    """Optional Venice pass — edgier, still minimal. Falls back to input on failure."""
    if not aof_copy_llm_enabled() or not (text or "").strip():
        return text
    try:
        from app.services.aof_copy_llm import sharpen_main_group_copy_sync

        return sharpen_main_group_copy_sync(text)
    except Exception:
        return text


def sharpen_variations(variations: list[str], *, use_llm: bool | None = None) -> list[str]:
    if use_llm is None:
        use_llm = aof_copy_llm_enabled()
    if not use_llm:
        return variations
    out: list[str] = []
    for v in variations:
        sharpened = maybe_llm_sharpen_copy(v)
        out.append(sharpened if sharpened else v)
    return out
