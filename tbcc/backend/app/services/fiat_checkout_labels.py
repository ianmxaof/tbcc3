"""User-facing labels for card/USD checkout (Gumroad backend — never say Gumroad in Telegram copy)."""

from __future__ import annotations

import os
import re

_GUMROAD_WORD = re.compile(r"\bgumroad\b", re.I)

_DEFAULT_BUTTON = "💳 Card / USD"
_DEFAULT_DISPLAY = "Card / USD"
_DEFAULT_SHORT = "Card"
_DEFAULT_OPEN_PAY = "Pay with card →"
_DEFAULT_CHECKOUT_TITLE = "Card checkout"


def _default_vip_link() -> str:
    from app.data.aof_vip_membership import vip_display_name

    return f"AOF {vip_display_name()} — card / USD"


def fiat_checkout_button_label(*, price_hint: str | None = None) -> str:
    """Inline keyboard label for VIP/card checkout row."""
    raw = (
        (os.getenv("TBCC_FIAT_CHECKOUT_BUTTON_LABEL") or "").strip()
        or (os.getenv("TBCC_GUMROAD_CHECKOUT_BUTTON_LABEL") or "").strip()
    )
    if raw and not _GUMROAD_WORD.search(raw):
        return raw[:64]
    if price_hint:
        return f"💳 Card / USD — {price_hint}"[:64]
    return _DEFAULT_BUTTON[:64]


def fiat_checkout_plan_button_label(duration_badge: str, *, price_hint: str | None = None) -> str:
    if price_hint:
        return f"💳 Pay {price_hint} · {duration_badge}"[:64]
    return f"💳 Card · {duration_badge}"[:64]


def fiat_checkout_display_name() -> str:
    return (
        (os.getenv("TBCC_FIAT_CHECKOUT_DISPLAY_NAME") or "").strip() or _DEFAULT_DISPLAY
    )[:64]


def fiat_checkout_short_name() -> str:
    return (os.getenv("TBCC_FIAT_CHECKOUT_SHORT_NAME") or "").strip() or _DEFAULT_SHORT


def fiat_open_pay_button_label() -> str:
    raw = (os.getenv("TBCC_FIAT_OPEN_PAY_BUTTON_LABEL") or "").strip()
    if raw and not _GUMROAD_WORD.search(raw):
        return raw[:64]
    return _DEFAULT_OPEN_PAY[:64]


def fiat_checkout_title() -> str:
    return _DEFAULT_CHECKOUT_TITLE


def fiat_vip_link_label() -> str:
    raw = (os.getenv("TBCC_FIAT_VIP_LINK_LABEL") or "").strip()
    if raw and not _GUMROAD_WORD.search(raw):
        return raw
    return _default_vip_link()


def fiat_vip_ladder_intro_html(*, include_intro: bool = False) -> str:
    from app.data.telegram_stars_howto import stars_howto_html, vip_intro_stars
    from app.data.aof_vip_membership import (
        VIP_INTRO_SKU,
        VIP_MEMBERSHIP_SKUS,
        vip_display_name,
        vip_intro_period_label,
    )

    disp = fiat_checkout_display_name()
    tier = vip_display_name()
    period = vip_intro_period_label()
    howto = stars_howto_html(compact=True)
    intro_usd = int(VIP_INTRO_SKU.price_usd)
    intro_stars = vip_intro_stars()
    monthly = int(VIP_MEMBERSHIP_SKUS[0].price_usd)
    # No ladder pitch on the first screen: one recurring month, priced from the SKUs.
    if include_intro:
        return (
            f"✨ <b>First {period} ${intro_usd}</b> (~{intro_stars}⭐) — new members only.\n"
            f"🔑 Then <b>${monthly}</b>/month on Stars / crypto / <b>{disp}</b>.\n\n"
            f"{howto}\n\n"
            f"Pick your entry:"
        )
    return (
        f"🔑 <b>AOF {tier}</b> — <b>${monthly}</b>/month on Stars / crypto / <b>{disp}</b>.\n\n"
        f"{howto}\n\n"
        f"Pick your entry:"
    )


def fiat_checkout_disabled_message() -> str:
    return "Card checkout is not enabled right now. Use Stars or crypto."


def fiat_checkout_not_configured_message() -> str:
    return (
        "Card checkout URL is not configured on the server. "
        "Use Stars or crypto, or contact support."
    )


def fiat_checkout_pay_instructions_html(*, title: str, tier_hint: str | None = None) -> str:
    disp = html_escape(fiat_checkout_display_name())
    title_e = html_escape(title)
    tier_line = ""
    if tier_hint:
        tier_line = f"\n3) On checkout choose <b>{html_escape(tier_hint)}</b> for this term."
    from app.data.aof_vip_membership import vip_display_name

    tier = html_escape(vip_display_name())
    return (
        f"<b>{title_e}</b> — pay with <b>{disp}</b> (card / PayPal).\n\n"
        f"1) Tap <b>{html_escape(fiat_open_pay_button_label())}</b> and complete payment\n"
        f"2) Keep this chat open — {tier} invite DMs here after payment confirms"
        f"{tier_line}"
    )


def fiat_checkout_confirm_footer_html() -> str:
    from app.data.aof_vip_membership import vip_display_name

    tier = html_escape(vip_display_name())
    return (
        f"After payment confirms, your {tier} invite lands here automatically. "
        f"Need help? Reply in this chat."
    )


def scrub_gumroad_from_user_copy(text: str) -> str:
    """Last-resort sanitizer for operator-authored HTML that still says Gumroad."""
    if not text or not _GUMROAD_WORD.search(text):
        return text
    out = _GUMROAD_WORD.sub(fiat_checkout_display_name(), text)
    out = out.replace("Card / USD VIP", "Card / USD VIP")  # idempotent
    out = re.sub(r"\bon on\b", "on", out, flags=re.I)
    return out


def html_escape(s: str) -> str:
    import html

    return html.escape(str(s or ""), quote=False)
