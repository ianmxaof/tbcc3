"""Telegram Stars checkout for companion photo generations."""

from __future__ import annotations

import os

from telegram import Bot, LabeledPrice


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


async def send_photo_invoice(bot: Bot, *, chat_id: int, user_id: int) -> None:
    stars = stars_per_photo()
    title = "Companion photo reveal"
    desc = "One AI photo generation on @aof_spicybot_bot"
    await bot.send_invoice(
        chat_id=chat_id,
        title=title[:32],
        description=desc[:255],
        payload=invoice_payload(user_id),
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=title[:64], amount=stars)],
    )
