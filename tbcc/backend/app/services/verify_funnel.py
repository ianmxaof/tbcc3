"""Verify funnel — channel CTA → bot → tap → invite or VIP checkout (Telegram-native)."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_network import MAIN_GROUP_INVITE, MAINHUB_RAW
from app.services.human_gate_pacing import (
    GATE_TARGETS,
    human_ack_callback_data,
    record_human_ack,
    resolve_gate_invite_url,
)
from app.services.subscription_access import is_aof_vip_subscriber

VERIFY_FUNNEL_SCHED_NAME = "AOF — verify funnel pin"
VERIFY_START_VIP = "verify_vip"
VERIFY_START_LOOT = "verify_loot"
VERIFY_START_DEFAULT = "verify"


def verify_funnel_enabled() -> bool:
    raw = (os.getenv("TBCC_VERIFY_FUNNEL_ENABLED") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def payment_bot_username() -> str:
    return (
        (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "").strip().lstrip("@")
        or "aofsubscriptions_bot"
    )


def verify_deep_link(target: str = "vip") -> str:
    """Public CTA deep link for channel pins / X (use verify_loot for Loot Room only)."""
    t = (target or "vip").strip().lower()
    payload = VERIFY_START_LOOT if t in ("loot", "loot_room", "main") else VERIFY_START_VIP
    return f"https://t.me/{payment_bot_username()}?start={payload}"


def parse_verify_start_payload(payload: str) -> str | None:
    """Map /start deep links to gate targets. None = not a verify handoff."""
    p = (payload or "").strip().lower()
    if p in (VERIFY_START_DEFAULT, "verify_access", "tap_verify", "collab", "collabland"):
        return "vip"
    if p in (VERIFY_START_VIP, "verify_premium", "verify_subscribe"):
        return "vip"
    if p in (VERIFY_START_LOOT, "verify_room", "verify_hub"):
        return "loot_room"
    return None


def verify_welcome_html(target: str) -> str:
    """Bot welcome after ?start=verify_* deep link."""
    from app.data.aof_vip_membership import vip_display_name

    t = (target or "vip").strip().lower()
    if t == "loot_room":
        return (
            "<b>AOF Loot Room</b>\n\n"
            "Tap <b>Continue</b> below — we'll send your invite link.\n\n"
            "<i>Free commons. Paid loot keys live in the same bot menu.</i>"
        )
    if t == "mainhub":
        return (
            "<b>AOF Mainhub</b>\n\n"
            "Tap <b>Continue</b> below — we'll send the hub link.\n\n"
            "<i>Network map + pinned links bulletin.</i>"
        )
    tier = vip_display_name()
    return (
        f"<b>AOF {tier}</b>\n\n"
        "Tap <b>Continue</b> below.\n\n"
        f"Active {tier} members get the private channel invite. "
        "New here? Stars checkout unlocks access in-app.\n\n"
        "<i>@aofsubscriptions_bot — real checkout, not a mod impersonator.</i>"
    )


def verify_button_label() -> str:
    return "✅ Continue"


def verify_ack_callback_data(target: str) -> str:
    return human_ack_callback_data(target)


def _vip_upgrade_keyboard_rows(db: Session) -> list[list[dict[str, str]]]:
    from app.data.aof_vip_membership import vip_display_name
    from app.services.aof_social_links import gumroad_vip_url
    from app.services.stars_bait_copy import StarsBaitProduct, checkout_start_payload, resolve_bait_plan_ids

    pay = payment_bot_username()
    plan_ids = resolve_bait_plan_ids(db)
    stars_payload = checkout_start_payload(StarsBaitProduct.SUBSCRIPTION, plan_ids)
    rows: list[list[dict[str, str]]] = [
        [{"text": f"⭐ Subscribe — {vip_display_name()} (Stars)", "url": f"https://t.me/{pay}?start={stars_payload}"}],
    ]
    card = (gumroad_vip_url() or "").strip()
    if card.startswith("https://"):
        rows.append([{"text": "💳 Pay with card", "url": card}])
    rows.append([{"text": "🗝 Loot Room keys", "url": f"https://t.me/{pay}?start=verify_loot"}])
    from app.services.bot_network_discovery import network_deep_link_url

    network = network_deep_link_url()
    if network:
        rows.append([{"text": "🌐 Explore AOF network", "url": network}])
    return rows


def post_verify_response_html(
    db: Session,
    *,
    telegram_user_id: int,
    target: str,
    already: bool = False,
) -> tuple[str, list[list[dict[str, str]]] | None]:
    """
    After Tap to Verify: invite for free lanes; VIP lane checks active subscription first.
    Returns (html, optional_inline_keyboard).
    """
    t = (target or "vip").strip().lower()
    if t not in GATE_TARGETS:
        t = "loot_room"

    from app.data.aof_vip_membership import vip_display_name

    invite_url, label = resolve_gate_invite_url(t)
    prefix = "You're already verified." if already else "Verified — you're in."
    tier = vip_display_name()

    if t == "vip":
        if is_aof_vip_subscriber(db, int(telegram_user_id)):
            return (
                f"✅ <b>{prefix}</b>\n\n"
                f"Your {tier} access is active. Join <b>{label}</b>:\n"
                f'<a href="{invite_url}">Open AOF {tier} channel</a>\n\n'
                "<i>Honest promos only — never fake Telegram staff.</i>",
                None,
            )
        return (
            f"✅ <b>{prefix}</b>\n\n"
            f"<b>AOF {tier}</b> — private broadcast channel.\n"
            "Subscribe below to get your invite.\n\n"
            f'Free feed: <a href="{MAIN_GROUP_INVITE}">Loot Room</a> · '
            f'<a href="{MAINHUB_RAW}">Mainhub</a>',
            _vip_upgrade_keyboard_rows(db),
        )

    return (
        f"✅ <b>{prefix}</b>\n\n"
        f"<b>{label}</b>:\n"
        f'<a href="{invite_url}">Open channel</a>\n\n'
        f'{tier} broadcast: <a href="{verify_deep_link("vip")}">@aofsubscriptions_bot</a>',
        None,
    )


def build_loot_room_verify_pin_html() -> str:
    """Pinned Loot Room access CTA."""
    from app.data.aof_vip_membership import vip_display_name

    vip_link = verify_deep_link("vip")
    loot_link = verify_deep_link("loot_room")
    pay = payment_bot_username()
    tier = vip_display_name()
    return (
        "<b>AOF — access lanes</b>\n\n"
        f"<b>{tier}</b> — private broadcast. Bigger drops, fewer gates. "
        "Start in the bot → subscribe → channel invite.\n\n"
        "<b>Loot Room</b> — free commons + overseer pulls. "
        f"Keys and rolls: <b>@aof_lootgod_bot</b>\n\n"
        f'👉 <a href="{vip_link}"><b>Join {tier}</b></a>\n'
        f'👉 <a href="{loot_link}"><b>Loot / keys</b></a>\n'
        f'👉 <a href="https://t.me/{pay}">@{pay}</a>'
    )


def record_verify_ack(
    db: Session,
    *,
    telegram_user_id: int,
    gate_target: str,
    source: str | None = None,
    username: str | None = None,
    first_name: str | None = None,
):
    """Persist consent via human_gate (DM outreach pool)."""
    return record_human_ack(
        db,
        telegram_user_id=telegram_user_id,
        gate_target=gate_target,
        source=(source or "verify_funnel")[:64],
        username=username,
        first_name=first_name,
    )
