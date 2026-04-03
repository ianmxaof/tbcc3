"""
Flashy /shop promo: hero + section images (env + per-product promo_image_url) + FOMO copy + CTA keyboard.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


def _api_base() -> str:
    return os.getenv("TBCC_API_URL", "http://localhost:8000").rstrip("/")

# Default urgency copy (Markdown). Override with SHOP_HERO_CAPTION (multi-line).
DEFAULT_HERO_CAPTION = (
    "🔥 **You’re one tap from the good stuff.**\n\n"
    "⏳ **Limited spots** — we don’t keep the door open forever.\n"
    "💎 **Premium** = full group / channel access.\n"
    "📦 **Packs** = exclusive drops — grab them before they rotate out.\n\n"
    "_**Telegram Stars** in-app (live). **Crypto** & **card (fiat)** — same catalog, rails rolling out._"
)


def _strip_md_for_log(s: str, max_len: int = 80) -> str:
    return (s or "").replace("\n", " ")[:max_len]


async def _fetch_plans_raw() -> list[dict]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{_api_base()}/subscription-plans/", timeout=15.0)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("shop_promo: failed to fetch plans: %s", e)
        return []


def _active_subs(plans: list[dict]) -> list[dict]:
    out = []
    for p in plans:
        if p.get("is_active") is False:
            continue
        if (p.get("price_stars") or 0) <= 0:
            continue
        if (p.get("product_type") or "subscription").lower() != "subscription":
            continue
        out.append(p)
    return out


def _active_bundles(plans: list[dict]) -> list[dict]:
    out = []
    for p in plans:
        if p.get("is_active") is False:
            continue
        if (p.get("price_stars") or 0) <= 0:
            continue
        if (p.get("product_type") or "").lower() != "bundle":
            continue
        out.append(p)
    return out


def _min_stars(products: list[dict]) -> int | None:
    if not products:
        return None
    return min(int(p.get("price_stars") or 0) for p in products)


async def _safe_send_photo(bot: Any, chat_id: int, photo_url: str, caption: str, parse_mode: str = "Markdown") -> bool:
    """Return True if Telegram accepted the photo URL."""
    try:
        await bot.send_photo(
            chat_id=chat_id,
            photo=photo_url.strip(),
            caption=caption[:1024],
            parse_mode=parse_mode,
        )
        return True
    except Exception as e:
        logger.warning("shop_promo: send_photo failed %s — %s", _strip_md_for_log(photo_url), e)
        return False


def _shop_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💎 Premium — unlock access", callback_data="menu_subscribe"),
                InlineKeyboardButton("📦 Digital packs", callback_data="menu_packs"),
            ],
            [
                InlineKeyboardButton("🔗 Referral rewards", callback_data="menu_referral"),
                InlineKeyboardButton("📋 My status", callback_data="menu_status"),
            ],
        ]
    )


async def send_shop_promo(update: Any, context: Any) -> None:
    """
    Send promotional sequence: optional hero image, section teasers, CTA + keyboard.
    """
    msg = update.effective_message
    if not msg:
        return
    chat_id = msg.chat_id
    bot = context.bot

    raw = await _fetch_plans_raw()
    subs = _active_subs(raw)
    bundles = _active_bundles(raw)
    min_sub = _min_stars(subs)
    min_pack = _min_stars(bundles)

    hero_url = (os.getenv("SHOP_HERO_IMAGE_URL") or "").strip()
    hero_caption = (os.getenv("SHOP_HERO_CAPTION") or "").strip() or DEFAULT_HERO_CAPTION

    # Dynamic price line (optional)
    price_bits = []
    if min_sub is not None:
        price_bits.append(f"Subscriptions from **{min_sub}** ⭐")
    if min_pack is not None:
        price_bits.append(f"Packs from **{min_pack}** ⭐")
    if price_bits:
        hero_caption = hero_caption + "\n\n" + " · ".join(price_bits)

    # --- Hero ---
    if hero_url:
        ok = await _safe_send_photo(bot, chat_id, hero_url, hero_caption)
        if not ok:
            await msg.reply_text(hero_caption, parse_mode="Markdown")
    else:
        await msg.reply_text(hero_caption, parse_mode="Markdown")

    # --- Section images (env overrides per category) ---
    sub_img_url = (os.getenv("SHOP_SUBSCRIPTION_IMAGE_URL") or "").strip()
    pack_img_url = (os.getenv("SHOP_PACKS_IMAGE_URL") or "").strip()

    if not sub_img_url:
        for p in subs:
            u = (p.get("promo_image_url") or "").strip()
            if u:
                sub_img_url = u
                break

    if not pack_img_url:
        for p in bundles:
            u = (p.get("promo_image_url") or "").strip()
            if u:
                pack_img_url = u
                break

    sub_caption = (
        (os.getenv("SHOP_SUBSCRIPTION_CAPTION") or "").strip()
        or "**Premium access** — stay inside the group, new drops first.\n"
        "Tap **Premium — unlock access** below before the next price bump."
    )
    pack_caption = (
        (os.getenv("SHOP_PACKS_CAPTION") or "").strip()
        or "**Digital packs** — curated image & video sets.\n"
        "_When they’re gone, they’re gone._"
    )

    # Telegram albums only show one caption — send separate photos for full copy per section.
    if sub_img_url and pack_img_url and sub_img_url == pack_img_url:
        combined = f"{sub_caption}\n\n{pack_caption}"
        await _safe_send_photo(bot, chat_id, sub_img_url, combined)
    else:
        if sub_img_url:
            await _safe_send_photo(bot, chat_id, sub_img_url, sub_caption)
        if pack_img_url:
            await _safe_send_photo(bot, chat_id, pack_img_url, pack_caption)

    if not sub_img_url and not pack_img_url and (subs or bundles):
        # No images: short text teasers
        lines = []
        if subs:
            lines.append("💎 **Premium** — subscription to the private channel / group.")
        if bundles:
            lines.append("📦 **Packs** — one-time bundles; grab them in the next step.")
        if lines:
            await bot.send_message(chat_id=chat_id, text="\n\n".join(lines), parse_mode="Markdown")

    # --- Final CTA ---
    cta = (
        "👇 **Choose your move** — unlock fast with **Stars** today; **crypto** & **fiat** checkout lands on the same products.\n"
        "_Not ready? Use /referral for your code + link and earn rewards._"
    )
    await bot.send_message(
        chat_id=chat_id,
        text=cta,
        parse_mode="Markdown",
        reply_markup=_shop_keyboard(),
    )


def shop_keyboard() -> InlineKeyboardMarkup:
    """Exported for payment_bot if needed."""
    return _shop_keyboard()
