"""Telegram Stars checkout for companion photo generations."""

from __future__ import annotations

import logging
import os

import httpx
from telegram import Bot, LabeledPrice

logger = logging.getLogger(__name__)


def stars_enabled() -> bool:
    raw = (os.getenv("TBCC_COMPANION_STARS_ENABLED") or "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return stars_per_photo() > 0


def stars_per_photo() -> int:
    raw = (os.getenv("TBCC_COMPANION_STARS_PER_PHOTO") or "25").strip()
    try:
        return max(0, min(10_000, int(raw)))
    except ValueError:
        return 25


def invoice_payload(user_id: int) -> str:
    return f"companion_photo_{int(user_id)}"


def parse_invoice_payload(payload: str) -> int | None:
    raw = (payload or "").strip()
    if not raw.startswith("companion_photo_"):
        return None
    parts = raw.split("_")
    if len(parts) != 3 or not parts[2].isdigit():
        return None
    return int(parts[2])


def validate_pre_checkout(*, invoice_payload_raw: str, buyer_user_id: int, currency: str, total_amount: int) -> tuple[bool, str]:
    uid = parse_invoice_payload(invoice_payload_raw)
    if uid is None:
        return False, "Unknown product"
    if uid != int(buyer_user_id):
        return False, "This invoice is for another user"
    expected = stars_per_photo()
    if currency != "XTR":
        return False, "Stars only"
    if total_amount != expected:
        return False, "Price changed — try again"
    return True, ""


def _invoice_fields(*, user_id: int) -> dict:
    stars = stars_per_photo()
    title = "Companion photo reveal"
    desc = "One AI photo generation on @aof_spicybot_bot"
    return {
        "title": title[:32],
        "description": desc[:255],
        "payload": invoice_payload(user_id),
        "provider_token": "",
        "currency": "XTR",
        "prices": [{"label": title[:64], "amount": stars}],
    }


async def send_photo_invoice(bot: Bot, *, chat_id: int, user_id: int) -> None:
    fields = _invoice_fields(user_id=user_id)
    await bot.send_invoice(
        chat_id=chat_id,
        title=fields["title"],
        description=fields["description"],
        payload=fields["payload"],
        provider_token=fields["provider_token"],
        currency=fields["currency"],
        prices=[LabeledPrice(label=fields["prices"][0]["label"], amount=int(fields["prices"][0]["amount"]))],
    )


def _bot_token() -> str:
    return (
        (os.getenv("TBCC_COMPANION_BOT_TOKEN") or "").strip()
        or (os.getenv("COMPANION_BOT_TOKEN") or "").strip()
    )


async def send_photo_invoice_http(*, chat_id: int, user_id: int) -> bool:
    """Send Stars invoice via Bot HTTP API (webhook/delivery path — no PTB bot handle)."""
    token = _bot_token()
    if not token or not stars_enabled():
        return False
    fields = _invoice_fields(user_id=user_id)
    payload = {"chat_id": int(chat_id), **fields}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"https://api.telegram.org/bot{token}/sendInvoice", json=payload)
        if r.is_success:
            return True
        logger.warning("sendInvoice http failed %s: %s", r.status_code, (r.text or "")[:300])
    except Exception as e:
        logger.warning("sendInvoice http error: %s", e)
    return False


async def maybe_offer_stars_after_delivery(*, chat_id: int, user_id: int) -> bool:
    """
    After a free/paid reveal lands, if the user has no allowance left, send the
    Stars invoice immediately — the conversion moment, not a buried /buy.
    Also surfaces loot + VIP bridge CTAs for Undress funnel users.
    """
    from app.services.operator_sandbox import skip_stars_checkout

    if skip_stars_checkout(user_id):
        return False
    if not stars_enabled():
        return False
    try:
        from app.services.companion_access import get_access

        if get_access(int(user_id)).generations_remaining() > 0:
            return False
    except Exception as e:
        logger.debug("stars upsell access check skipped: %s", e)
        return False

    from app.services.companion_monetize_cta import (
        companion_exhaustion_cta_html,
        companion_exhaustion_reply_markup,
    )
    from app.services.companion_telegram_dispatch import send_result_message

    stars = stars_per_photo()
    await send_result_message(
        chat_id=int(chat_id),
        text=(
            f"Free trial used — next reveal is {stars}⭐.\n"
            "Pay the invoice below (or /buy anytime). /referral earns free credits."
        ),
        parse_mode=None,
    )
    sent = await send_photo_invoice_http(chat_id=int(chat_id), user_id=int(user_id))
    try:
        from app.database.session import SessionLocal
        from app.services.companion_access import affiliate_undress_url_wrapped

        db = SessionLocal()
        try:
            undress = affiliate_undress_url_wrapped(db=db)
        finally:
            db.close()
        cta = companion_exhaustion_cta_html(include_undress=bool(undress), undress_url=undress)
        markup = companion_exhaustion_reply_markup()
        if cta:
            await send_result_message(
                chat_id=int(chat_id),
                text=cta,
                reply_markup=markup,
            )
    except Exception as e:
        logger.debug("companion exhaustion CTA skipped: %s", e)
    return sent
