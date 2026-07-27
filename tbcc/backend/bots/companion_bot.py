"""
NSFW companion Telegram bot — LLM chat + undress/nudify image generation.

Architecture (per NSFW chatbot best practices):
- Private DM only; short-term chat memory via python-telegram-bot user_data
- Async image jobs via undresstool.fun and/or nudify.me webhooks → TBCC API → DM delivery
- Rate limits + 18+ attestation on /start

Run: cd tbcc/backend && python -m bots.companion_bot

Env:
  TBCC_COMPANION_BOT_TOKEN (required)
  TBCC_UNDRESS_TOOL_API_KEY — undresstool.fun (https://public-api.undresstool.fun/docs)
  TBCC_NUDIFY_API_KEY — optional nudify.me provider
  TBCC_COMPANION_IMAGE_PROVIDER=undress|nudify
  TBCC_PUBLIC_API_BASE_URL — public https root for webhooks (ngrok in dev)
  TBCC_LLM_CHAT_* — same as llm_chat_bot for text persona
"""
from __future__ import annotations

import logging
import os
import sys
import time
from collections import deque
from io import BytesIO
from pathlib import Path

_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from dotenv import load_dotenv

_env = Path(__file__).resolve().parent.parent.parent / ".env"
if _env.exists():
    load_dotenv(_env, override=True)

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from app.services.companion_access import (
    addlist_url,
    affiliate_undress_url,
    auto_complete_gate_if_ready,
    can_spend_operator_api,
    consume_generation_allowance,
    gate_enabled,
    gate_lv_url,
    get_access,
    main_group_invite_url,
    mark_lv_acknowledged,
    refund_generation_allowance,
    verify_aof_membership,
)
from app.services.companion_body_prefs import (
    CLOTH_OPTIONS,
    GROUP_LABELS,
    OPTION_GROUPS,
    apply_bimbo_preset,
    clear_body_prefs,
    display_value,
    load_body_prefs,
    option_button_label,
    save_body_pref,
    styles_help_text,
)
from app.services.companion_character import (
    character_mode_enabled,
    get_character,
    set_character_name,
)
from app.services.companion_referral import (
    maybe_credit_referrer_on_gate_complete,
    record_referral_by_code,
    referral_bonus_photos,
    referral_link,
    referrals_enabled,
)
from app.services.companion_stars import (
    parse_invoice_payload,
    send_photo_invoice,
    stars_enabled,
    stars_per_photo,
    validate_pre_checkout,
)

from app.services.companion_generation import (
    check_public_webhook_reachable,
    generation_configured,
    image_provider,
    queue_photo_generation,
)
from app.services.nudify_client import configured as nudify_configured
from app.services.llm_chat import complete_llm_chat, default_system_prompt, provider_configured
from app.services.undress_tool_client import (
    DEFAULT_PHOTO_POSES,
    configured as undress_configured,
    get_me,
    list_photo_poses,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

HISTORY_KEY = "companion_history"
AGE_KEY = "age_confirmed"
NAME_AWAIT_KEY = "awaiting_character_name"
POSE_KEY = "selected_pose"
POSE_OPTIONS_KEY = "pose_options"
BOT_USERNAME_KEY = "companion_bot_username"

_rate_log: dict[int, deque[float]] = {}


def _token() -> str:
    return (os.getenv("TBCC_COMPANION_BOT_TOKEN") or os.getenv("COMPANION_BOT_TOKEN") or "").strip()


def _rate_limit_per_minute() -> int:
    raw = (os.getenv("TBCC_COMPANION_RATE_LIMIT_PER_MIN") or os.getenv("TBCC_LLM_CHAT_RATE_LIMIT_PER_MIN") or "20").strip()
    try:
        return max(1, min(60, int(raw)))
    except ValueError:
        return 20


def _history_max() -> int:
    raw = (os.getenv("TBCC_COMPANION_HISTORY_MAX") or os.getenv("TBCC_LLM_CHAT_HISTORY_MAX_MESSAGES") or "24").strip()
    try:
        return max(2, min(48, int(raw)))
    except ValueError:
        return 24


def _allow_rate_limit(user_id: int) -> bool:
    cap = _rate_limit_per_minute()
    now = time.monotonic()
    dq = _rate_log.setdefault(user_id, deque())
    while dq and now - dq[0] > 60.0:
        dq.popleft()
    if len(dq) >= cap:
        return False
    dq.append(now)
    return True


def _age_confirmed(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return bool(context.user_data.get(AGE_KEY))


def _gate_keyboard() -> InlineKeyboardMarkup | None:
    lv = gate_lv_url()
    addlist = addlist_url()
    loot = main_group_invite_url()
    rows: list[list[InlineKeyboardButton]] = []
    if lv:
        rows.append([InlineKeyboardButton("1️⃣ Open AOF gate (Linkvertise)", url=lv)])
    if addlist:
        rows.append([InlineKeyboardButton("Join all AOF channels (addlist)", url=addlist)])
    if loot:
        rows.append([InlineKeyboardButton("Loot Room entry (verify fallback)", url=loot)])
    rows.append([InlineKeyboardButton("2️⃣ I completed the gate", callback_data="comp_gate_lv_done")])
    rows.append([InlineKeyboardButton("3️⃣ Verify channel membership", callback_data="comp_gate_verify")])
    return InlineKeyboardMarkup(rows) if rows else None


async def _reply_gate_required(msg, user_id: int, *, prefix: str = "") -> None:
    acc = get_access(user_id)
    head = prefix + "\n\n" if prefix else ""
    if acc.lv_ack and not acc.member_verified:
        step3 = (
            "3️⃣ Open <b>Loot Room entry</b> (button below) or any addlist channel, wait ~30s, "
            "then tap <b>Verify membership</b> — or send your photo again and I'll recheck.\n\n"
        )
        tail = "After Member ✅: confirm 18+ and send a photo, or chat freely."
    else:
        step3 = "3️⃣ Tap <b>I completed the gate</b>, then <b>Verify membership</b>\n\n"
        tail = "After verify: confirm 18+ and send a photo, or chat freely."
    text = (
        f"{head}<b>Welcome to @aof_spicybot_bot</b>\n\n"
        "Before chat or photo reveals, join the AOF stack — takes ~2 minutes:\n\n"
        "1️⃣ Tap <b>Open AOF gate</b> → complete Linkvertise\n"
        "2️⃣ Tap <b>Join all AOF channels</b> (addlist) — pick any lane\n"
        f"{step3}"
        f"Status: LV {'✅' if acc.lv_ack else '⏳'} · Member {'✅' if acc.member_verified else '⏳'}\n\n"
        f"{tail}"
    )
    await msg.reply_text(text, parse_mode="HTML", reply_markup=_gate_keyboard())


async def _gate_access(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Load access and auto-retry membership when LV is already complete."""
    return await auto_complete_gate_if_ready(context.bot, user_id)


def _selected_pose(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    raw = (context.user_data.get(POSE_KEY) or "").strip()
    return raw or None


def _companion_system_prompt(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> str:
    base = (os.getenv("TBCC_COMPANION_SYSTEM_PROMPT") or "").strip() or default_system_prompt()
    acc = get_access(user_id)
    pose = _selected_pose(context)
    body = load_body_prefs(context.user_data)
    lines = [base, ""]
    char = get_character(user_id)
    if char and character_mode_enabled():
        lines.extend(["[Character — stay in persona]", char.prompt_block(), ""])
    lines.append("[Runtime context — weave naturally; do not dump as a list]")
    lines.append(f"User photo allowance remaining: {acc.generations_remaining()}")
    if pose and not char:
        lines.append(f"User selected reveal style/pose: {pose}")
    if body.to_api_kwargs() and not char:
        lines.append(f"User body prefs: {body.summary()}")
    if stars_enabled():
        lines.append(f"Extra photos cost {stars_per_photo()} Telegram Stars via /buy")
    return "\n".join(lines)


def _start_menu_text(user_id: int, acc) -> str:
    vip_line = ""
    if acc.vip_subscriber:
        from app.services.aof_vip_perks import vip_companion_bonus_credits

        vip_line = (
            f"\n⭐ <b>VIP active</b> — Hall Pass lane. "
            f"Bonus credits on join: {vip_companion_bonus_credits()}. "
            f"Allowance now: {acc.generations_remaining()}."
        )
    text = (
        "<b>Create your character</b>\n\n"
        "1. Confirm you're <b>18+</b>\n"
        "2. <b>Body styles</b> → Bimbo preset (optional tuning)\n"
        "3. <b>Poses</b> — pick her vibe (e.g. Wet girl)\n"
        "4. <b>Send a photo</b> — she comes to life from your pic\n"
        "5. <b>Chat</b> — talk to her in first person; she remembers you\n\n"
        f"<b>Photo allowance</b>: {acc.generations_remaining()}\n"
        f"<b>Stars</b>: {stars_per_photo()}⭐ per extra reveal"
        f"{vip_line}"
    )
    char = get_character(user_id)
    if char:
        text += f"\n\n✨ <b>{char.name}</b> is live — just message her."
    else:
        text += "\n\n<i>No character yet — send a photo to create her.</i>"
    return text


def _main_menu_keyboard(context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    row1: list[InlineKeyboardButton] = []
    if not _age_confirmed(context):
        row1.append(InlineKeyboardButton("18+", callback_data="comp_menu:age"))
    row1.append(InlineKeyboardButton("Body styles", callback_data="comp_menu:styles"))
    row1.append(InlineKeyboardButton("Poses", callback_data="comp_menu:poses"))
    rows: list[list[InlineKeyboardButton]] = [row1]

    row2 = [
        InlineKeyboardButton("Rename", callback_data="comp_menu:name"),
        InlineKeyboardButton("Balance", callback_data="comp_menu:balance"),
    ]
    if stars_enabled():
        row2.append(InlineKeyboardButton("Buy reveal", callback_data="comp_menu:buy"))
    rows.append(row2)
    rows.append([InlineKeyboardButton("Clear chat memory", callback_data="comp_menu:reset")])
    return InlineKeyboardMarkup(rows)


def _age_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("I'm 18+", callback_data="comp_menu:age")]])


async def _send_start_menu(
    *,
    chat_id: int,
    user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    bot,
    edit_message_id: int | None = None,
) -> None:
    acc = get_access(user_id)
    text = _start_menu_text(user_id, acc)
    kb = _main_menu_keyboard(context)
    if edit_message_id is not None:
        await bot.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=edit_message_id,
            parse_mode="HTML",
            reply_markup=kb,
        )
    else:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=kb)


def _body_styles_keyboard(user_data: dict | None = None) -> InlineKeyboardMarkup:
    prefs = load_body_prefs(user_data or {})
    active = prefs.to_api_kwargs()
    rows: list[list[InlineKeyboardButton]] = []

    for group, options in OPTION_GROUPS.items():
        row: list[InlineKeyboardButton] = []
        for opt in options:
            row.append(
                InlineKeyboardButton(
                    option_button_label(group, opt, selected=active.get(group) == opt),
                    callback_data=f"comp_body:{group}:{opt}",
                )
            )
        rows.append(row)

    cloth_row: list[InlineKeyboardButton] = []
    for opt in CLOTH_OPTIONS:
        cloth_row.append(
            InlineKeyboardButton(
                option_button_label("cloth", opt, selected=active.get("cloth") == opt),
                callback_data=f"comp_body:cloth:{opt}",
            )
        )
        if len(cloth_row) >= 3:
            rows.append(cloth_row)
            cloth_row = []
    if cloth_row:
        rows.append(cloth_row)

    rows.append(
        [
            InlineKeyboardButton("Bimbo preset", callback_data="comp_body:preset:bimbo"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton("Clear all", callback_data="comp_body:clear"),
            InlineKeyboardButton("Done", callback_data="comp_body:done"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def _pose_keyboard(poses: list[str]) -> InlineKeyboardMarkup | None:
    if not poses:
        return None
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i, pose in enumerate(poses[:16]):
        label = pose if len(pose) <= 22 else pose[:19] + "…"
        row.append(InlineKeyboardButton(label, callback_data=f"comp_pose:{i}"))
        if len(row) >= 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("Default (no pose)", callback_data="comp_pose:clear")])
    return InlineKeyboardMarkup(rows)


async def _bot_username(context: ContextTypes.DEFAULT_TYPE) -> str:
    cached = context.application.bot_data.get(BOT_USERNAME_KEY)
    if cached:
        return str(cached)
    me = await context.bot.get_me()
    uname = (me.username or "aof_spicybot_bot").strip()
    context.application.bot_data[BOT_USERNAME_KEY] = uname
    return uname


async def _notify_referrer_credit(context: ContextTypes.DEFAULT_TYPE, result: dict) -> None:
    referrer_id = int(result.get("referrer_user_id") or 0)
    bonus = int(result.get("bonus_granted") or 0)
    if referrer_id <= 0 or bonus <= 0:
        return
    try:
        await context.bot.send_message(
            chat_id=referrer_id,
            text=(
                f"Referral reward: +{bonus} photo credit(s) — your invite completed the AOF gate.\n"
                f"Balance: {result.get('referrer_credits', '?')}"
            ),
        )
    except Exception as e:
        logger.debug("referrer notify failed: %s", e)


def _parse_start_arg(context: ContextTypes.DEFAULT_TYPE) -> str:
    return (context.args[0] if context.args else "").strip()


async def _handle_start_referral(update: Update, context: ContextTypes.DEFAULT_TYPE, arg: str) -> bool:
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg or not arg:
        return False
    low = arg.lower()
    if not low.startswith("compref_"):
        return False
    code = arg[8:].strip()
    if not code or not referrals_enabled():
        return False
    ok = record_referral_by_code(referred_user_id=int(user.id), code=code)
    if ok:
        await msg.reply_text(
            "Referral linked. Complete the AOF gate — your inviter earns bonus photo credits when you verify."
        )
    return ok


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    arg = _parse_start_arg(context)
    if arg:
        try:
            from app.services.traffic_attribution import record_traffic_touch_from_bot

            record_traffic_touch_from_bot(int(user.id), arg)
        except Exception:
            pass
        await _handle_start_referral(update, context, arg)
    acc = await _gate_access(context, user.id)
    if gate_enabled() and not acc.gate_complete:
        await _reply_gate_required(
            msg,
            user.id,
            prefix=(
                "<b>@aof_spicybot_bot</b> — create your character from a photo, then chat in private.\n"
                "18+ only. AOF VIP skips this gate + gets bonus credits — @aofsubscriptions_bot"
            ),
        )
        return
    acc = get_access(user.id)
    await _send_start_menu(chat_id=msg.chat_id, user_id=user.id, context=context, bot=context.bot)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_verify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if not get_access(user.id).lv_ack:
        await msg.reply_text("Complete the Linkvertise gate first, then tap verify.", reply_markup=_gate_keyboard())
        return
    ok, channel = await verify_aof_membership(context.bot, user.id)
    if ok:
        acc = get_access(user.id)
        credit = maybe_credit_referrer_on_gate_complete(user.id)
        if credit:
            await _notify_referrer_credit(context, credit)
        await msg.reply_text(
            f"Verified — you're in <b>{channel}</b>.\n"
            f"Photo allowance: <b>{acc.generations_remaining()}</b> (trial + credits).\n"
            "Now confirm 18+ and send a photo, or chat freely.",
            parse_mode="HTML",
        )
    else:
        await msg.reply_text(
            "I can't see you in any AOF channel yet.\n"
            "Join one from the addlist, wait ~30s, then /verify again.",
            reply_markup=_gate_keyboard(),
        )


async def on_gate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return
    await query.answer()
    if query.data == "comp_gate_lv_done":
        mark_lv_acknowledged(user.id)
        await query.edit_message_text(
            "Gate marked complete. Join an AOF channel, then tap verify.",
            reply_markup=_gate_keyboard(),
        )
        return
    if query.data == "comp_gate_verify":
        if not get_access(user.id).lv_ack:
            await query.answer("Complete the LV gate first.", show_alert=True)
            return
        ok, channel = await verify_aof_membership(context.bot, user.id)
        if ok:
            acc = get_access(user.id)
            credit = maybe_credit_referrer_on_gate_complete(user.id)
            if credit:
                await _notify_referrer_credit(context, credit)
            await query.edit_message_text(
                f"Verified in {channel}. Allowance: {acc.generations_remaining()} photos. Confirm 18+ then send a pic.",
            )
        else:
            await query.answer("Not in an AOF channel yet — join addlist first.", show_alert=True)
            acc = get_access(user.id)
            await query.edit_message_text(
                "I can't see you in any AOF channel yet.\n"
                "Join one from the addlist, wait ~30s, then tap verify again.\n\n"
                f"Status: LV {'✅' if acc.lv_ack else '⏳'} · Member {'✅' if acc.member_verified else '⏳'}",
                reply_markup=_gate_keyboard(),
            )


async def cmd_referral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if not referrals_enabled():
        await msg.reply_text("Referrals are off.")
        return
    uname = await _bot_username(context)
    link = referral_link(uname, user.id)
    bonus = referral_bonus_photos()
    await msg.reply_text(
        f"<b>Your invite link</b>\n{link}\n\n"
        f"When a friend completes the AOF gate (LV + channel verify), you earn "
        f"<b>+{bonus}</b> photo credit(s).",
        parse_mode="HTML",
    )


async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if not stars_enabled():
        aff = affiliate_undress_url()
        await msg.reply_text(
            "Stars checkout is off."
            + (f"\n\nUse affiliate undress bot:\n{aff}" if aff else "")
        )
        return
    acc = await _gate_access(context, user.id)
    if gate_enabled() and not acc.gate_complete:
        await _reply_gate_required(msg, user.id)
        return
    await send_photo_invoice(context.bot, chat_id=msg.chat_id, user_id=user.id)


async def cmd_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    context.user_data[AGE_KEY] = True
    await msg.reply_text(
        "18+ confirmed — send a photo when you're ready.",
        reply_markup=_main_menu_keyboard(context),
    )

async def _send_pose_picker(
    *,
    bot,
    chat_id: int,
    user_data: dict,
    note: str = "",
) -> None:
    poses: list[str] = []
    used_fallback = False
    try:
        poses = await list_photo_poses()
    except Exception as e:
        logger.warning("list_photo_poses failed: %s", e)
        poses = list(DEFAULT_PHOTO_POSES)
        used_fallback = True
    if not poses:
        await bot.send_message(chat_id=chat_id, text="No poses available right now — try again later.")
        return
    user_data[POSE_OPTIONS_KEY] = poses[:24]
    kb = _pose_keyboard(poses)
    preview = ", ".join(poses[:8])
    extra = f" … +{len(poses) - 8} more" if len(poses) > 8 else ""
    fallback_note = "\n<i>(Pose list from cache — provider was briefly unavailable.)</i>\n" if used_fallback else ""
    await bot.send_message(
        chat_id=chat_id,
        text=f"{note}<b>Pick a pose</b>{fallback_note}\n{preview}{extra}",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def on_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user or not query.data:
        return
    action = query.data.split(":", 1)[1]
    chat_id = query.message.chat_id if query.message else user.id

    if action == "age":
        context.user_data[AGE_KEY] = True
        await query.answer("18+ confirmed")
        if query.message:
            await _send_start_menu(
                chat_id=chat_id,
                user_id=user.id,
                context=context,
                bot=context.bot,
                edit_message_id=query.message.message_id,
            )
        return

    if action == "styles":
        await query.answer()
        prefs = load_body_prefs(context.user_data)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{styles_help_text()}\n\n<b>Current</b>\n{prefs.summary()}",
            parse_mode="HTML",
            reply_markup=_body_styles_keyboard(context.user_data),
        )
        return

    if action == "poses":
        await query.answer()
        await _send_pose_picker(bot=context.bot, chat_id=chat_id, user_data=context.user_data)
        return

    if action == "name":
        char = get_character(user.id)
        if not char:
            await query.answer("Send a photo first to create her.", show_alert=True)
            return
        await query.answer()
        context.user_data[NAME_AWAIT_KEY] = True
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Her name is <b>{char.name}</b>.\nWhat should I call her? Reply with just the new name.",
            parse_mode="HTML",
        )
        return

    if action == "balance":
        await query.answer()
        acc = get_access(user.id)
        lines = [
            f"<b>Your allowance</b>: {acc.generations_remaining()} photo(s)",
            f"Trial used: {acc.trial_used} · Bonus credits: {acc.credits}",
        ]
        if stars_enabled():
            lines.append(f"Extra reveals: {stars_per_photo()}⭐ — tap Buy reveal on the menu.")
        await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="HTML")
        return

    if action == "buy":
        if not stars_enabled():
            await query.answer("Stars checkout is off.", show_alert=True)
            return
        await query.answer()
        await send_photo_invoice(context.bot, chat_id=chat_id, user_id=user.id)
        return

    if action == "reset":
        context.user_data.pop(HISTORY_KEY, None)
        await query.answer("Chat memory cleared")
        await context.bot.send_message(
            chat_id=chat_id,
            text="Chat memory cleared — your character stays the same.\nSend a new photo to recreate her look.",
        )
        return

    await query.answer()


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    context.user_data.pop(HISTORY_KEY, None)
    await msg.reply_text(
        "Chat memory cleared — your character stays the same.\n"
        "Send a new photo to recreate her look."
    )


async def cmd_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    char = get_character(user.id)
    if not char:
        await msg.reply_text("Create her first — send a photo.", reply_markup=_main_menu_keyboard(context))
        return
    args = context.args or []
    if not args:
        context.user_data[NAME_AWAIT_KEY] = True
        await msg.reply_text(
            f"Her name is <b>{char.name}</b>.\nWhat should I call her? Reply with just the new name.",
            parse_mode="HTML",
        )
        return
    new_name = " ".join(args).strip()[:40]
    updated = set_character_name(user.id, new_name)
    if updated:
        await msg.reply_text(f"Done — you're chatting with <b>{updated.name}</b> now.", parse_mode="HTML")


async def cmd_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    lines = [
        f"Active image provider: <code>{image_provider()}</code>",
        f"Undress API: {'yes' if undress_configured() else 'no'}",
        f"Nudify API: {'yes' if nudify_configured() else 'no'}",
    ]
    await msg.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    acc = get_access(user.id)
    lines = [
        f"<b>Your allowance</b>: {acc.generations_remaining()} photo(s)",
        f"Trial used: {acc.trial_used} · Bonus credits: {acc.credits}",
    ]
    if stars_enabled():
        lines.append(f"Need more? Tap <b>Buy reveal</b> on the menu ({stars_per_photo()}⭐).")
    await msg.reply_text("\n".join(lines), parse_mode="HTML", reply_markup=_main_menu_keyboard(context))


async def cmd_poses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    selected = _selected_pose(context) or "default"
    await _send_pose_picker(
        bot=context.bot,
        chat_id=msg.chat_id,
        user_data=context.user_data,
        note=f"Current: <b>{selected}</b>\n\n",
    )


async def on_pose_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    if query.data == "comp_pose:clear":
        context.user_data.pop(POSE_KEY, None)
        await query.edit_message_text("Pose cleared — using default reveal style.")
        return
    if not query.data.startswith("comp_pose:"):
        return
    idx_raw = query.data.split(":", 1)[1]
    try:
        idx = int(idx_raw)
    except ValueError:
        return
    poses = context.user_data.get(POSE_OPTIONS_KEY) or []
    if idx < 0 or idx >= len(poses):
        await query.answer("Pose list expired — tap Poses on the menu again.", show_alert=True)
        return
    pose = str(poses[idx])
    context.user_data[POSE_KEY] = pose
    await query.edit_message_text(f"Style locked: <b>{pose}</b>. Send a photo when ready.", parse_mode="HTML")


async def cmd_styles(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    prefs = load_body_prefs(context.user_data)
    await msg.reply_text(
        f"{styles_help_text()}\n\n<b>Current</b>\n{prefs.summary()}",
        parse_mode="HTML",
        reply_markup=_body_styles_keyboard(context.user_data),
    )


async def on_body_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    if query.data == "comp_body:clear":
        await query.answer("Cleared")
        clear_body_prefs(context.user_data)
        await query.edit_message_text(
            "Body prefs cleared.",
            reply_markup=_body_styles_keyboard(context.user_data),
        )
        return
    if query.data == "comp_body:preset:bimbo":
        await query.answer("Bimbo preset locked")
        prefs = apply_bimbo_preset(context.user_data)
        await query.edit_message_text(
            f"{styles_help_text()}\n\n<b>Current</b>\n{prefs.summary()}",
            parse_mode="HTML",
            reply_markup=_body_styles_keyboard(context.user_data),
        )
        return
    if query.data == "comp_body:done":
        await query.answer()
        prefs = load_body_prefs(context.user_data)
        await query.edit_message_text(
            f"Locked in:\n<b>{prefs.summary()}</b>\n\n/poses for style · send photo when ready.",
            parse_mode="HTML",
        )
        return
    if not query.data.startswith("comp_body:"):
        await query.answer()
        return
    parts = query.data.split(":", 2)
    if len(parts) != 3:
        await query.answer()
        return
    _, group, value = parts
    prefs = save_body_pref(context.user_data, group, value)
    label = GROUP_LABELS.get(group, group)
    await query.answer(f"{label} → {display_value(group, getattr(prefs, group, None) or value)}")
    try:
        await query.edit_message_text(
            f"{styles_help_text()}\n\n<b>Current</b>\n{prefs.summary()}",
            parse_mode="HTML",
            reply_markup=_body_styles_keyboard(context.user_data),
        )
    except Exception:
        pass


async def on_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or not msg.text:
        return
    if msg.chat.type != "private":
        return
    acc = await _gate_access(context, user.id)
    if gate_enabled() and not acc.gate_complete:
        await _reply_gate_required(msg, user.id)
        return
    if not _allow_rate_limit(user.id):
        await msg.reply_text("Slow down — rate limit. Try again in a minute.")
        return
    if not provider_configured():
        await msg.reply_text("Chat isn't available right now — try again later.")
        return

    user_text = msg.text.strip()
    if not user_text:
        return

    if character_mode_enabled() and not get_character(user.id):
        await msg.reply_text(
            "I don't exist yet — send a photo to create me first.\n"
            "Tip: open the menu → Body styles → Bimbo preset, then Poses.",
            reply_markup=_main_menu_keyboard(context),
        )
        return

    if context.user_data.pop(NAME_AWAIT_KEY, False):
        char = get_character(user.id)
        if not char:
            await msg.reply_text("Create her with a photo first.")
            return
        new_name = user_text[:40]
        if not new_name:
            return
        updated = set_character_name(user.id, new_name)
        if updated:
            await msg.reply_text(
                f"Done — you're chatting with <b>{updated.name}</b> now.",
                parse_mode="HTML",
                reply_markup=_main_menu_keyboard(context),
            )
        return

    try:
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
    except Exception as e:
        logger.debug("send_chat_action: %s", e)

    hist: list[dict[str, str]] = context.user_data.get(HISTORY_KEY) or []
    hist = [m for m in hist if m.get("role") in ("user", "assistant", "system") and m.get("content")]

    messages: list[dict[str, str]] = [{"role": "system", "content": _companion_system_prompt(user.id, context)}]
    messages.extend(hist[-_history_max() :])
    messages.append({"role": "user", "content": user_text})

    try:
        reply = await complete_llm_chat(messages)
    except Exception as e:
        logger.warning("companion llm failed: %s", e)
        err = str(e)
        if "429" in err or "rate-limit" in err.lower():
            await msg.reply_text(
                "Model is rate-limited upstream — retry in a minute, or set "
                "TBCC_LLM_CHAT_FALLBACK_MODELS / TBCC_LLM_MODEL in .env."
            )
            return
        await msg.reply_text(f"Model error: {err[:4000]}")
        return

    await msg.reply_text((reply or "")[:4096])
    next_hist = hist + [{"role": "user", "content": user_text}, {"role": "assistant", "content": reply}]
    context.user_data[HISTORY_KEY] = next_hist[-(_history_max() * 2 + 4) :]


async def _photo_file_id(update: Update) -> tuple[str, str] | None:
    msg = update.effective_message
    if not msg:
        return None
    if msg.photo:
        return msg.photo[-1].file_id, "photo.jpg"
    doc = msg.document
    if doc and doc.mime_type and doc.mime_type.startswith("image/"):
        name = (doc.file_name or "photo.jpg").strip() or "photo.jpg"
        return doc.file_id, name
    return None


async def _download_file_id(context: ContextTypes.DEFAULT_TYPE, file_id: str, filename: str) -> tuple[bytes, str]:
    tg_file = await context.bot.get_file(file_id)
    buf = BytesIO()
    await tg_file.download_to_memory(out=buf)
    return buf.getvalue(), filename


async def _queue_user_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    photo_bytes: bytes,
    filename: str,
    status_msg,
) -> bool:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return False

    reachable, reach_detail = await check_public_webhook_reachable()
    if not reachable:
        await status_msg.edit_text(
            "Cannot reach your public webhook URL — results would never arrive.\n\n"
            f"{reach_detail}\n\n"
            "Fix: run <code>ngrok http 8000</code>, copy the https URL into "
            "<code>TBCC_PUBLIC_API_BASE_URL</code> in .env, restart API + bot.",
            parse_mode="HTML",
        )
        return False

    try:
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.UPLOAD_PHOTO)
    except Exception:
        pass

    if not consume_generation_allowance(user.id):
        await status_msg.edit_text("Allowance exhausted.")
        return False

    body = load_body_prefs(context.user_data)
    api = body.to_api_kwargs()
    try:
        queued = await queue_photo_generation(
            chat_id=msg.chat_id,
            user_id=user.id,
            photo_bytes=photo_bytes,
            filename=filename,
            pose=_selected_pose(context),
            age=api.get("age"),
            breast_size=api.get("breast_size"),
            body_type=api.get("body_type"),
            butt_size=api.get("butt_size"),
            cloth=api.get("cloth"),
        )
    except Exception as e:
        refund_generation_allowance(user.id)
        logger.warning("companion queue failed: %s", e)
        await status_msg.edit_text(f"Could not queue generation: {e!s}"[:4000])
        return False

    acc = get_access(user.id)
    pose_note = f"\nStyle: <code>{_selected_pose(context)}</code>" if _selected_pose(context) else ""
    body = load_body_prefs(context.user_data)
    body_note = f"\nBody: <code>{body.summary()}</code>" if body.to_api_kwargs() else ""
    await status_msg.edit_text(
        f"{queued.message}{pose_note}{body_note}\n\n"
        f"Reveals left: <b>{acc.generations_remaining()}</b>\n"
        "I'll DM her when she's ready.",
        parse_mode="HTML",
    )
    return True


async def _offer_paid_photo_path(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    file_id: str,
    filename: str,
) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if stars_enabled():
        save_pending_photo(user_id=user.id, chat_id=msg.chat_id, file_id=file_id, filename=filename)
        await send_photo_invoice(context.bot, chat_id=msg.chat_id, user_id=user.id)
        await msg.reply_text(
            f"Free trial used. Pay <b>{stars_per_photo()}⭐</b> above — I'll process this photo right after payment.\n"
            "Or /referral to earn credits by inviting friends.",
            parse_mode="HTML",
        )
        return
    aff = affiliate_undress_url()
    await msg.reply_text(
        "No free generations left on this bot.\n\n"
        + (f"Use the affiliate undress bot (your ref earns credits):\n{aff}" if aff else "Contact admin for credits.")
    )


async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    if not query or not query.from_user:
        return
    ok, err = validate_pre_checkout(
        invoice_payload_raw=query.invoice_payload or "",
        buyer_user_id=query.from_user.id,
        currency=query.currency,
        total_amount=int(query.total_amount),
    )
    if ok:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message=err or "Payment unavailable")


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    payment = msg.successful_payment if msg else None
    if not msg or not user or not payment:
        return
    uid = parse_invoice_payload(payment.invoice_payload or "")
    if uid is None or uid != user.id:
        await msg.reply_text("Payment received — thank you!")
        return

    charge_id = (getattr(payment, "telegram_payment_charge_id", None) or "").strip() or None
    stars = int(getattr(payment, "total_amount", 0) or 0)

    def _record_income() -> None:
        from app.database.session import SessionLocal
        from app.services.income_ledger import record_companion_stars_income

        db = SessionLocal()
        try:
            record_companion_stars_income(db, user_id=user.id, stars=stars, charge_id=charge_id)
        finally:
            db.close()

    import asyncio

    try:
        await asyncio.to_thread(_record_income)
    except Exception:
        pass

    from app.services.companion_access import grant_credits

    grant_credits(user.id, 1)
    pending = pop_pending_photo(user.id)
    if not pending:
        await msg.reply_text("Credit added. Send a photo when you're ready.")
        return

    acc = await _gate_access(context, user.id)
    if gate_enabled() and not acc.gate_complete:
        await msg.reply_text("Complete the AOF gate first (/start), then send the photo again.")
        return
    if not _age_confirmed(context):
        context.user_data[AGE_KEY] = True

    status_msg = await msg.reply_text("Payment received — queuing your photo…")
    photo_bytes, filename = await _download_file_id(
        context,
        str(pending["file_id"]),
        str(pending.get("filename") or "photo.jpg"),
    )
    await _queue_user_photo(
        update,
        context,
        photo_bytes=photo_bytes,
        filename=filename,
        status_msg=status_msg,
    )


async def _download_photo_bytes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[bytes, str] | None:
    msg = update.effective_message
    if not msg:
        return None
    if msg.photo:
        photo = msg.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)
        buf = BytesIO()
        await tg_file.download_to_memory(out=buf)
        return buf.getvalue(), "photo.jpg"
    doc = msg.document
    if doc and doc.mime_type and doc.mime_type.startswith("image/"):
        tg_file = await context.bot.get_file(doc.file_id)
        buf = BytesIO()
        await tg_file.download_to_memory(out=buf)
        name = (doc.file_name or "photo.jpg").strip() or "photo.jpg"
        return buf.getvalue(), name
    return None


async def on_private_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if msg.chat.type != "private":
        return
    if not _age_confirmed(context):
        await msg.reply_text(
            "Confirm you're 18+ first.",
            reply_markup=_age_confirm_keyboard(),
        )
        return
    acc = await _gate_access(context, user.id)
    if gate_enabled() and not acc.gate_complete:
        await _reply_gate_required(msg, user.id)
        return
    allowed, reason = can_spend_operator_api(user.id)
    if not allowed:
        if reason == "complete_gate":
            await _reply_gate_required(msg, user.id)
            return
        if reason == "no_credits":
            fid = await _photo_file_id(update)
            if fid:
                await _offer_paid_photo_path(update, context, file_id=fid[0], filename=fid[1])
            else:
                await msg.reply_text("No allowance left. Use /buy or /referral.")
            return
    if not _allow_rate_limit(user.id):
        await msg.reply_text("Slow down — rate limit.")
        return
    if not generation_configured():
        await msg.reply_text("Photo reveals aren't available right now — try again later.")
        return

    status_msg = await msg.reply_text("Got your photo — checking tunnel and queuing…")

    downloaded = await _download_photo_bytes(update, context)
    if not downloaded:
        await status_msg.edit_text("Send a photo or image document.")
        return
    photo_bytes, filename = downloaded

    await _queue_user_photo(
        update,
        context,
        photo_bytes=photo_bytes,
        filename=filename,
        status_msg=status_msg,
    )


async def post_init(app: Application) -> None:
    me = await app.bot.get_me()
    logger.info("companion bot online @%s id=%s provider=%s", me.username, me.id, image_provider())
    commands = [
        BotCommand("start", "Create your character"),
        BotCommand("menu", "Open button menu"),
        BotCommand("help", "How it works"),
        BotCommand("verify", "Verify AOF membership"),
        BotCommand("referral", "Invite friends"),
    ]
    try:
        await app.bot.set_my_commands(commands)
    except Exception as e:
        logger.warning("set_my_commands: %s", e)


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


def main() -> None:
    token = _token()
    if not token:
        print("Set TBCC_COMPANION_BOT_TOKEN in tbcc/.env")
        return

    app = Application.builder().token(token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("verify", cmd_verify))
    app.add_handler(CommandHandler("referral", cmd_referral))
    app.add_handler(CommandHandler("buy", cmd_buy))
    app.add_handler(CallbackQueryHandler(on_gate_callback, pattern=r"^comp_gate_"))
    app.add_handler(CallbackQueryHandler(on_menu_callback, pattern=r"^comp_menu:"))
    app.add_handler(CallbackQueryHandler(on_pose_callback, pattern=r"^comp_pose:"))
    app.add_handler(CallbackQueryHandler(on_body_callback, pattern=r"^comp_body:"))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(CommandHandler("age", cmd_age))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("name", cmd_name))
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("styles", cmd_styles))
    app.add_handler(CommandHandler("poses", cmd_poses))
    # Legacy slash commands — menu buttons are the primary UI.
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.PHOTO, on_private_photo))
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.Document.IMAGE,
            on_private_photo,
        )
    )
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & (~filters.COMMAND), on_private_text))

    print("Companion bot running. Image provider:", image_provider())
    print("Webhooks need TBCC_PUBLIC_API_BASE_URL reachable from the internet.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
