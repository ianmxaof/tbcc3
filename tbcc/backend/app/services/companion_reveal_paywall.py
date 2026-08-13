"""Reveal paywall — Stars/referral copy only after photo allowance is exhausted."""

from __future__ import annotations

import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from app.services.companion_access import affiliate_undress_url_wrapped
from app.services.companion_monetize_cta import (
    companion_exhaustion_cta_html,
    companion_exhaustion_inline_keyboard_rows,
)
from app.services.companion_credit_checkout import companion_credit_pack_button_rows
from app.services.companion_referral import (
    referral_bonus_photos,
    referral_link,
    referral_require_invitee_reveal,
    referrals_enabled,
)
from app.services.companion_stars import send_photo_invoice, stars_enabled, stars_per_photo
from app.services.operator_sandbox import skip_stars_checkout

logger = logging.getLogger(__name__)


def reveal_paywall_lines() -> list[str]:
    """HTML lines for balance view when allowance is zero."""
    lines: list[str] = []
    if stars_enabled():
        lines.append(
            f"Buy one reveal now: <b>{stars_per_photo()}⭐</b> — tap <b>Reveal</b> or /buy."
        )
        lines.append("Or grab a <b>credit pack</b> below (Stars + crypto via payment bot).")
    elif companion_credit_pack_button_rows():
        lines.append("Top up with a <b>credit pack</b> below (Stars + crypto).")
    if referrals_enabled():
        bonus = referral_bonus_photos()
        lines.append(
            f"Or invite friends — earn <b>+{bonus}</b> credit(s) when they complete the gate"
            f"{' and send their first reveal' if referral_require_invitee_reveal() else ''}."
        )
    return lines


def reveal_paywall_keyboard(*, bot_username: str, user_id: int) -> InlineKeyboardMarkup | None:
    """Loot/VIP bridge + credit packs + invite-friends row for exhaustion moment."""
    rows: list[list[InlineKeyboardButton]] = []
    for pack_row in companion_credit_pack_button_rows():
        rows.append([InlineKeyboardButton(text=btn["text"], url=btn["url"]) for btn in pack_row])
    if referrals_enabled():
        link = referral_link(bot_username, user_id)
        rows.append([InlineKeyboardButton("🔗 Invite friends (earn credits)", url=link)])
    for row in companion_exhaustion_inline_keyboard_rows():
        rows.append([InlineKeyboardButton(text=btn["text"], url=btn["url"]) for btn in row])
    return InlineKeyboardMarkup(rows) if rows else None


async def send_reveal_paywall(
    bot: Bot,
    *,
    chat_id: int,
    user_id: int,
    pending_photo: bool = False,
    bot_username: str = "aof_spicybot_bot",
) -> None:
    if skip_stars_checkout(user_id):
        await bot.send_message(
            chat_id=chat_id,
            text="Operator QA — send a photo; no Stars needed.",
            parse_mode="HTML",
        )
        return

    from app.database.session import SessionLocal

    db = SessionLocal()
    try:
        aff = affiliate_undress_url_wrapped(db=db)
    finally:
        db.close()
    cta = companion_exhaustion_cta_html(include_undress=bool(aff), undress_url=aff)
    kb = reveal_paywall_keyboard(bot_username=bot_username, user_id=user_id)

    if stars_enabled():
        await send_photo_invoice(bot, chat_id=chat_id, user_id=user_id)
        if pending_photo:
            pay_line = (
                f"Free trial used. Pay <b>{stars_per_photo()}⭐</b> above — "
                "I'll reveal her from your photo right after payment."
            )
        else:
            pay_line = (
                f"No reveals left. Pay <b>{stars_per_photo()}⭐</b> above — "
                "I'll process your next photo right after."
            )
    else:
        pay_line = "No free reveals left on this bot."

    ref_line = ""
    if referrals_enabled():
        bonus = referral_bonus_photos()
        reveal_note = " and send their first reveal" if referral_require_invitee_reveal() else ""
        ref_line = (
            f"\nOr tap <b>Invite friends</b> below — earn <b>+{bonus}</b> credit(s) when "
            f"a friend completes the AOF gate{reveal_note}."
        )

    await bot.send_message(chat_id=chat_id, text=pay_line + ref_line, parse_mode="HTML", reply_markup=kb)
    if cta:
        await bot.send_message(chat_id=chat_id, text=cta, parse_mode="HTML")
