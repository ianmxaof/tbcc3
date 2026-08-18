"""Canonical Telegram Stars purchase education for AOF checkout surfaces.

Adapted from swipe ``telegram-stars-howto-vip-pricing-v1`` (competitor pricing/bots
stripped). Entry price doctrine: surface the **$10 intro** (~834⭐) everywhere VIP
is sold; standard ladder starts at $18 / ~1500⭐.
"""

from __future__ import annotations

import math
import os

from app.data.aof_vip_membership import VIP_INTRO_SKU, VIP_MEMBERSHIP_SKUS, vip_display_name

STARS_HOWTO_SNIPPET_TITLE = "[AOF] How to buy Telegram Stars"


def stars_usd_per_star() -> float:
    raw = (os.getenv("TBCC_STARS_USD_PER_STAR") or "0.012").strip()
    try:
        return max(0.001, min(0.05, float(raw)))
    except ValueError:
        return 0.012


def usd_to_stars_ceil(usd: float) -> int:
    rate = stars_usd_per_star()
    return max(1, int(math.ceil(float(usd) / rate)))


def vip_intro_stars() -> int:
    return usd_to_stars_ceil(VIP_INTRO_SKU.price_usd)


def vip_monthly_stars() -> int:
    return usd_to_stars_ceil(VIP_MEMBERSHIP_SKUS[0].price_usd)


def stars_howto_html(*, compact: bool = False) -> str:
    """HTML block for payment-bot / Insiders captions (Telegram HTML)."""
    from app.data.aof_vip_membership import vip_intro_period_label

    intro_usd = int(VIP_INTRO_SKU.price_usd) if VIP_INTRO_SKU.price_usd == int(VIP_INTRO_SKU.price_usd) else VIP_INTRO_SKU.price_usd
    intro_stars = vip_intro_stars()
    tier = vip_display_name()
    period = vip_intro_period_label()
    if compact:
        return (
            f"⚠️ <b>Need Stars?</b> Buy them in Telegram with a credit/debit card "
            f"(Settings → My Stars, or the ⭐ on any invoice) — then tap Pay.\n"
            f"✨ {tier} starts at <b>${intro_usd}</b> / <b>{intro_stars}⭐</b> (first {period} intro)."
        )
    return (
        f"⚠️ <b>Paying with Telegram Stars</b>\n"
        f"✅ Stars can be bought with a credit/debit card <b>inside Telegram</b>\n"
        f"✅ Settings → <b>My Stars</b> (or tap ⭐ on any invoice) → Buy Stars\n"
        f"✅ Come back here and tap <b>Pay ⭐</b>\n\n"
        f"✨ <b>{tier} from ${intro_usd}</b> — first {period} intro (~{intro_stars}⭐). "
        f"Standard renews from ${int(VIP_MEMBERSHIP_SKUS[0].price_usd)}."
    )


def stars_howto_plain() -> str:
    """Plain-text variant for caption_snippets / Buffer."""
    from app.data.aof_vip_membership import vip_intro_period_label

    intro_usd = int(VIP_INTRO_SKU.price_usd)
    intro_stars = vip_intro_stars()
    monthly = int(VIP_MEMBERSHIP_SKUS[0].price_usd)
    return (
        "⚠️ Paying with Telegram Stars?\n"
        "✅ Buy Stars with a credit/debit card inside Telegram\n"
        "✅ Settings → My Stars (or tap ⭐ on any invoice) → Buy Stars\n"
        "✅ Return and tap Pay ⭐\n\n"
        f"✨ AOF {vip_display_name()} starts at ${intro_usd} / ~{intro_stars}⭐ (first {vip_intro_period_label()} intro).\n"
        f"Standard ladder from ${monthly}/mo.\n"
        "👉 /subscribe on @aofsubscriptions_bot"
    )


def stars_pay_entry_button_label(*, price_stars: int, plan_name: str | None = None) -> str:
    """Inline button label — lead with $10 intro when that SKU is the plan."""
    from app.data.aof_vip_membership import is_vip_intro_plan_name

    stars = int(price_stars or 0)
    if is_vip_intro_plan_name(plan_name):
        usd = int(VIP_INTRO_SKU.price_usd)
        tier = vip_display_name()
        if stars > 0:
            return f"{tier} ${usd} · {stars}⭐"[:64]
        return f"{tier} ${usd} intro"[:64]
    if stars > 0:
        return f"Pay ⭐ {stars}"[:64]
    return "Pay with Stars"


def ensure_stars_howto_caption_snippet(db) -> dict:
    """Idempotent insert of Stars how-to into caption_snippets library."""
    from app.models.caption_snippet import CaptionSnippet

    title = STARS_HOWTO_SNIPPET_TITLE
    body = stars_howto_plain()
    existing = db.query(CaptionSnippet).filter(CaptionSnippet.title == title).first()
    if existing:
        if (existing.body or "").strip() != body.strip():
            existing.body = body[:16000]
            db.add(existing)
            db.commit()
            db.refresh(existing)
            return {"created": False, "updated": True, "id": existing.id, "title": title}
        return {"created": False, "updated": False, "id": existing.id, "title": title}
    row = CaptionSnippet(title=title, body=body[:16000])
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"created": True, "updated": False, "id": row.id, "title": title}

