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
    affiliate_undress_url_wrapped,
    auto_complete_gate_if_ready,
    can_spend_operator_api,
    consume_generation_allowance,
    gate_enabled,
    gate_lv_url,
    get_access,
    main_group_invite_url,
    mark_lv_acknowledged,
    refund_generation_allowance,
    touch_companion_activity,
    verify_aof_membership,
)
from app.services.companion_body_prefs import (
    BODY_PRESET_IDS,
    apply_body_preset,
    clear_body_prefs,
    load_body_prefs,
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
    referral_link,
    referral_reward_description,
    referrals_enabled,
)
from app.services.companion_reveal_paywall import reveal_paywall_lines, send_reveal_paywall
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
    queue_video_generation,
    video_credit_units,
    video_enabled,
)
from app.services.companion_menu import (
    body_preset_keyboard,
    hero_image_path,
    main_menu_keyboard,
    pose_keyboard,
    repeat_menu_hint_text,
    start_menu_text,
    video_pose_keyboard,
    welcome_caption,
)
from app.services.companion_assets import ensure_preset_card, list_pose_tile_paths
from app.services.nudify_client import configured as nudify_configured
from app.services.llm_chat import complete_llm_chat, default_system_prompt, provider_configured
from app.services.undress_tool_client import (
    DEFAULT_PHOTO_POSES,
    configured as undress_configured,
    get_me,
    list_photo_poses,
    list_video_poses,
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
MEDIA_MODE_KEY = "media_mode"
VIDEO_POSE_KEY = "video_pose"
VIDEO_POSE_OPTIONS_KEY = "video_pose_options"
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
    from app.services.operator_sandbox import skip_companion_rate_limit

    if skip_companion_rate_limit(user_id):
        return True
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
    if stars_enabled() and acc.generations_remaining() <= 0:
        lines.append(
            f"User has no reveals left — next reveal costs {stars_per_photo()} Stars or /referral credits"
        )
    return "\n".join(lines)


def _media_mode(context: ContextTypes.DEFAULT_TYPE) -> str:
    raw = (context.user_data.get(MEDIA_MODE_KEY) or "photo").strip().lower()
    return "video" if raw == "video" else "photo"


def _selected_video_pose(context: ContextTypes.DEFAULT_TYPE) -> dict[str, str] | None:
    raw = context.user_data.get(VIDEO_POSE_KEY)
    if isinstance(raw, dict) and raw.get("id"):
        return {"id": str(raw["id"]), "name": str(raw.get("name") or raw["id"])}
    return None


def _main_menu_keyboard(context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    return main_menu_keyboard(
        age_confirmed=_age_confirmed(context),
        video_enabled=video_enabled(),
    )


def _start_menu_text(user_id: int, acc) -> str:
    from app.services.operator_sandbox import companion_allowance_label, operator_status_line

    vip_line = ""
    if acc.vip_subscriber and not operator_status_line(user_id):
        from app.services.aof_vip_perks import vip_companion_bonus_credits

        vip_line = (
            f"\n⭐ <b>VIP active</b> — bonus credits on join: {vip_companion_bonus_credits()}."
        )
    allowance = companion_allowance_label(user_id)
    op_line = operator_status_line(user_id)
    char = get_character(user_id)
    text = start_menu_text(
        allowance=allowance,
        character_name=char.name if char else None,
        vip_line=vip_line,
        op_line=op_line or "",
    )
    return text


async def _send_start_menu(
    *,
    chat_id: int,
    user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    bot,
    edit_message_id: int | None = None,
) -> None:
    acc = get_access(user_id)
    touch_companion_activity(user_id)
    text = _start_menu_text(user_id, acc)
    kb = _main_menu_keyboard(context)
    if edit_message_id is not None:
        try:
            await bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=edit_message_id,
                parse_mode="HTML",
                reply_markup=kb,
            )
            return
        except Exception:
            pass
    hero = hero_image_path()
    if hero and hero.is_file():
        from app.services.operator_sandbox import companion_allowance_label

        char = get_character(user_id)
        with hero.open("rb") as photo_file:
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo_file,
                caption=welcome_caption(
                    allowance=companion_allowance_label(user_id),
                    character_name=char.name if char else None,
                ),
                parse_mode="HTML",
                reply_markup=kb,
            )
        return
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=kb)


def _age_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ I'm 18+", callback_data="comp_menu:age")]])


async def _send_body_preset_picker(*, bot, chat_id: int, user_data: dict) -> None:
    prefs = load_body_prefs(user_data)
    from telegram import InputMediaPhoto

    media: list[InputMediaPhoto] = []
    for preset_id in BODY_PRESET_IDS:
        path = ensure_preset_card(preset_id)
        with path.open("rb") as f:
            media.append(InputMediaPhoto(media=f.read(), caption=preset_label_card(preset_id)))
    if media:
        try:
            await bot.send_media_group(chat_id=chat_id, media=media[:3])
        except Exception as e:
            logger.debug("preset media group skipped: %s", e)
    await bot.send_message(
        chat_id=chat_id,
        text=f"{styles_help_text()}\n\n<b>Current</b>\n{prefs.summary()}",
        parse_mode="HTML",
        reply_markup=body_preset_keyboard(user_data),
    )


def preset_label_card(preset_id: str) -> str:
    labels = {"natural": "Natural", "curvy": "Curvy", "bimbo": "Bimbo max"}
    return labels.get(preset_id, preset_id)


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
    if referrer_id <= 0:
        return
    bonus = int(result.get("bonus_granted") or 0)
    try:
        if result.get("deferred_until_reveal"):
            await context.bot.send_message(
                chat_id=referrer_id,
                text=(
                    "Your invite completed the AOF gate — you'll earn photo credits "
                    "when they send their first reveal."
                ),
            )
            return
        if bonus <= 0:
            return
        reason = (
            "your invite sent their first reveal"
            if result.get("credit_reason") == "first_reveal"
            else "your invite completed the AOF gate"
        )
        await context.bot.send_message(
            chat_id=referrer_id,
            text=(
                f"Referral reward: +{bonus} photo credit(s) — {reason}.\n"
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
    if arg == "missed_you":
        acc = await _gate_access(context, user.id)
        touch_companion_activity(user.id)
        if gate_enabled() and not acc.gate_complete:
            await _reply_gate_required(
                msg,
                user.id,
                prefix="I missed you too 🥰 — finish the quick gate first, then we can talk.",
            )
            return
        await msg.reply_text(
            "Hey you 🥰 I'm glad you're back.\n\n"
            "Talk to me here — or send a photo if you want to pick up where we left off.",
            parse_mode="HTML",
            reply_markup=_main_menu_keyboard(context),
        )
        return
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
        touch_companion_activity(user.id)
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
    await msg.reply_text(
        f"<b>Your invite link</b>\n{link}\n\n{referral_reward_description()}",
        parse_mode="HTML",
    )


async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if not stars_enabled():
        from app.database.session import SessionLocal
        from app.services.companion_monetize_cta import (
            companion_exhaustion_cta_html,
            companion_exhaustion_inline_keyboard,
        )

        db = SessionLocal()
        try:
            aff = affiliate_undress_url_wrapped(db=db)
        finally:
            db.close()
        cta = companion_exhaustion_cta_html(include_undress=bool(aff), undress_url=aff)
        kb = companion_exhaustion_inline_keyboard()
        await msg.reply_text(
            "Stars checkout is off.\n\n" + (cta or "Try Loot God or VIP below."),
            parse_mode="HTML",
            reply_markup=kb,
        )
        return
    acc = await _gate_access(context, user.id)
    if gate_enabled() and not acc.gate_complete:
        await _reply_gate_required(msg, user.id)
        return
    from app.services.operator_sandbox import operator_status_line, skip_stars_checkout

    if skip_stars_checkout(user.id):
        await msg.reply_text(
            operator_status_line(user.id) or "Operator QA — unlimited reveals; no Stars needed.",
            parse_mode="HTML",
        )
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
    selected: str | None = None,
) -> None:
    from telegram import InputMediaPhoto

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
    sel = selected or user_data.get(POSE_KEY)
    kb = pose_keyboard(poses, selected=str(sel) if sel else None)
    fallback_note = "\n<i>(Pose list from cache — provider was briefly unavailable.)</i>\n" if used_fallback else ""
    preview_paths = list_pose_tile_paths(poses[:10])
    if preview_paths:
        media: list[InputMediaPhoto] = []
        for i, path in enumerate(preview_paths):
            caption = f"{i + 1}. {poses[i]}" if i < len(poses) else None
            with path.open("rb") as f:
                media.append(InputMediaPhoto(media=f.read(), caption=caption))
        try:
            await bot.send_media_group(chat_id=chat_id, media=media)
        except Exception as e:
            logger.debug("pose gallery skipped: %s", e)
    await bot.send_message(
        chat_id=chat_id,
        text=f"{note}<b>Pick a photo pose</b>{fallback_note}",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def _send_video_pose_picker(
    *,
    bot,
    chat_id: int,
    user_data: dict,
    note: str = "",
) -> None:
    if not video_enabled():
        await bot.send_message(chat_id=chat_id, text="Video reveals aren't available right now.")
        return
    poses: list[dict[str, str]] = []
    try:
        poses = await list_video_poses()
    except Exception as e:
        logger.warning("list_video_poses failed: %s", e)
        poses = []
    if not poses:
        await bot.send_message(chat_id=chat_id, text="No video poses available right now — try again later.")
        return
    user_data[VIDEO_POSE_OPTIONS_KEY] = poses[:12]
    selected = _selected_video_pose_from_data(user_data)
    kb = video_pose_keyboard(poses, selected_id=selected.get("id") if selected else None)
    await bot.send_message(
        chat_id=chat_id,
        text=f"{note}<b>Pick a video pose</b>\n<i>Video uses {video_credit_units()} reveal credits.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )


def _selected_video_pose_from_data(user_data: dict) -> dict[str, str] | None:
    raw = user_data.get(VIDEO_POSE_KEY)
    if isinstance(raw, dict) and raw.get("id"):
        return {"id": str(raw["id"]), "name": str(raw.get("name") or raw["id"])}
    return None


async def on_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user or not query.data:
        return
    action = query.data.split(":", 1)[1]
    chat_id = query.message.chat_id if query.message else user.id

    if action == "home":
        await query.answer()
        await _send_start_menu(
            chat_id=chat_id,
            user_id=user.id,
            context=context,
            bot=context.bot,
        )
        return

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
        await _send_body_preset_picker(bot=context.bot, chat_id=chat_id, user_data=context.user_data)
        return

    if action == "poses":
        await query.answer()
        context.user_data[MEDIA_MODE_KEY] = "photo"
        await _send_pose_picker(
            bot=context.bot,
            chat_id=chat_id,
            user_data=context.user_data,
            selected=_selected_pose(context),
        )
        return

    if action == "video":
        await query.answer()
        if not video_enabled():
            await query.answer("Video is off — check API balance.", show_alert=True)
            return
        context.user_data[MEDIA_MODE_KEY] = "video"
        await _send_video_pose_picker(bot=context.bot, chat_id=chat_id, user_data=context.user_data)
        return

    if action == "chat_hint":
        await query.answer()
        await context.bot.send_message(
            chat_id=chat_id,
            text="Just type here — she replies in first person and remembers you.\nSend a photo anytime for a new reveal.",
            reply_markup=_main_menu_keyboard(context),
        )
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
        if acc.generations_remaining() <= 0:
            lines.extend(reveal_paywall_lines())
        await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="HTML")
        return

    if action in ("buy", "reveal"):
        await query.answer()
        context.user_data[MEDIA_MODE_KEY] = "photo"
        acc = get_access(user.id)
        units = video_credit_units() if _media_mode(context) == "video" else 1
        if acc.generations_remaining() >= units:
            mode = "video" if _media_mode(context) == "video" else "photo"
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Send a photo — I'll create her {mode} reveal.",
                parse_mode="HTML",
                reply_markup=_main_menu_keyboard(context),
            )
            return
        uname = await _bot_username(context)
        await send_reveal_paywall(
            context.bot,
            chat_id=chat_id,
            user_id=user.id,
            bot_username=uname,
        )
        return

    if action == "referral":
        await query.answer()
        if not referrals_enabled():
            await context.bot.send_message(chat_id=chat_id, text="Referrals are off.")
            return
        uname = await _bot_username(context)
        link = referral_link(uname, user.id)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"<b>Your invite link</b>\n{link}\n\n{referral_reward_description()}",
            parse_mode="HTML",
        )
        return

    if action == "reset":
        context.user_data.pop(HISTORY_KEY, None)
        await query.answer("Chat memory cleared")
        await context.bot.send_message(
            chat_id=chat_id,
            text="Chat memory cleared — your character stays the same.\nSend a new photo to recreate her look.",
            reply_markup=_main_menu_keyboard(context),
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
    from app.services.operator_sandbox import (
        companion_allowance_label,
        operator_status_line,
        skip_stars_checkout,
    )

    acc = get_access(user.id)
    lines = [f"<b>Your allowance</b>: {companion_allowance_label(user.id)} photo(s)"]
    if not skip_stars_checkout(user.id):
        lines.append(f"Trial used: {acc.trial_used} · Bonus credits: {acc.credits}")
        if acc.generations_remaining() <= 0:
            lines.extend(reveal_paywall_lines())
    op_line = operator_status_line(user.id)
    if op_line:
        lines.append(f"<i>{op_line}</i>")
    await msg.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=_main_menu_keyboard(context),
    )


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
    context.user_data[MEDIA_MODE_KEY] = "photo"
    await query.edit_message_text(
        f"Style locked: <b>{pose}</b>. Send a photo when ready.",
        parse_mode="HTML",
        reply_markup=_main_menu_keyboard(context),
    )


async def cmd_styles(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    await _send_body_preset_picker(bot=context.bot, chat_id=msg.chat_id, user_data=context.user_data)


async def on_preset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    if query.data == "comp_preset:clear":
        await query.answer("Cleared")
        clear_body_prefs(context.user_data)
        prefs = load_body_prefs(context.user_data)
        await query.edit_message_text(
            f"{styles_help_text()}\n\n<b>Current</b>\n{prefs.summary()}",
            parse_mode="HTML",
            reply_markup=body_preset_keyboard(context.user_data),
        )
        return
    if query.data == "comp_preset:done":
        await query.answer()
        prefs = load_body_prefs(context.user_data)
        await query.edit_message_text(
            f"Locked in:\n<b>{prefs.summary()}</b>\n\nPick a pose or send a photo when ready.",
            parse_mode="HTML",
            reply_markup=_main_menu_keyboard(context),
        )
        return
    if not query.data.startswith("comp_preset:"):
        await query.answer()
        return
    preset_id = query.data.split(":", 1)[1]
    if preset_id not in BODY_PRESET_IDS:
        await query.answer()
        return
    await query.answer(f"Preset: {preset_label_card(preset_id)}")
    prefs = apply_body_preset(context.user_data, preset_id)
    try:
        await query.edit_message_text(
            f"{styles_help_text()}\n\n<b>Current</b>\n{prefs.summary()}",
            parse_mode="HTML",
            reply_markup=body_preset_keyboard(context.user_data),
        )
    except Exception:
        pass


async def on_vpose_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    if query.data == "comp_vpose:clear":
        context.user_data.pop(VIDEO_POSE_KEY, None)
        context.user_data[MEDIA_MODE_KEY] = "video"
        await query.edit_message_text("Video pose cleared — default motion reveal.")
        return
    if not query.data.startswith("comp_vpose:"):
        return
    try:
        idx = int(query.data.split(":", 1)[1])
    except ValueError:
        return
    poses = context.user_data.get(VIDEO_POSE_OPTIONS_KEY) or []
    if idx < 0 or idx >= len(poses):
        await query.answer("Pose list expired — open Video reveal again.", show_alert=True)
        return
    pose = poses[idx]
    context.user_data[VIDEO_POSE_KEY] = {"id": str(pose.get("id")), "name": str(pose.get("name") or pose.get("id"))}
    context.user_data[MEDIA_MODE_KEY] = "video"
    await query.edit_message_text(
        f"Video pose locked: <b>{pose.get('name')}</b>. Send a photo when ready.",
        parse_mode="HTML",
        reply_markup=_main_menu_keyboard(context),
    )


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
    touch_companion_activity(user.id)
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
            "Tip: open the menu → Body preset → Pick pose, then send a photo.",
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

    media_mode = _media_mode(context)
    credit_units = video_credit_units() if media_mode == "video" else 1
    ok, referral_credit = consume_generation_allowance(user.id, units=credit_units)
    if not ok:
        await status_msg.edit_text(
            f"Allowance exhausted — video needs {credit_units} reveal credit(s)."
            if media_mode == "video"
            else "Allowance exhausted."
        )
        return False
    if referral_credit and int(referral_credit.get("bonus_granted") or 0) > 0:
        await _notify_referrer_credit(context, referral_credit)

    body = load_body_prefs(context.user_data)
    api = body.to_api_kwargs()
    logger.info(
        "companion bot queue uid=%s mode=%s pose=%s api_params=%s",
        user.id,
        media_mode,
        _selected_pose(context) if media_mode == "photo" else _selected_video_pose(context),
        api,
    )
    try:
        if media_mode == "video":
            vpose = _selected_video_pose(context)
            queued = await queue_video_generation(
                chat_id=msg.chat_id,
                user_id=user.id,
                photo_bytes=photo_bytes,
                filename=filename,
                video_pose_id=vpose.get("id") if vpose else None,
                video_pose_name=vpose.get("name") if vpose else None,
            )
        else:
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
        refund_generation_allowance(user.id, units=credit_units)
        logger.warning("companion queue failed: %s", e)
        await status_msg.edit_text(f"Could not queue generation: {e!s}"[:4000])
        return False

    acc = get_access(user.id)
    pose_note = ""
    if media_mode == "video":
        vpose = _selected_video_pose(context)
        if vpose:
            pose_note = f"\nVideo pose: <code>{vpose.get('name')}</code>"
    elif _selected_pose(context):
        pose_note = f"\nStyle: <code>{_selected_pose(context)}</code>"
    body_note = f"\nBody: <code>{body.summary()}</code>" if body.to_api_kwargs() else ""
    await status_msg.edit_text(
        f"{queued.message}{pose_note}{body_note}\n\n"
        f"Reveals left: <b>{acc.generations_remaining()}</b>\n"
        "I'll DM her when she's ready.",
        parse_mode="HTML",
        reply_markup=_main_menu_keyboard(context),
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
    from app.services.operator_sandbox import skip_stars_checkout

    if skip_stars_checkout(user.id):
        await msg.reply_text(
            "Operator QA — send another photo; no Stars invoice.",
            parse_mode="HTML",
        )
        return
    if stars_enabled():
        save_pending_photo(
            user_id=user.id,
            chat_id=msg.chat_id,
            file_id=file_id,
            filename=filename,
            media_type=_media_mode(context),
        )
    uname = await _bot_username(context)
    await send_reveal_paywall(
        context.bot,
        chat_id=msg.chat_id,
        user_id=user.id,
        pending_photo=bool(stars_enabled()),
        bot_username=uname,
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
    except Exception as e:
        logger.exception(
            "companion Stars income ledger failed uid=%s stars=%s charge=%s: %s",
            user.id,
            stars,
            charge_id,
            e,
        )

    from app.services.companion_access import grant_credits

    grant_credits(user.id, 1)
    touch_companion_activity(user.id)
    pending = pop_pending_photo(user.id)
    if not pending:
        await msg.reply_text("Credit added. Send a photo when you're ready.")
        return

    if pending.get("media_type") == "video":
        context.user_data[MEDIA_MODE_KEY] = "video"

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
    touch_companion_activity(user.id)
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
                uname = await _bot_username(context)
                await send_reveal_paywall(
                    context.bot,
                    chat_id=msg.chat_id,
                    user_id=user.id,
                    bot_username=uname,
                )
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
        BotCommand("buy", "Buy another photo reveal (Stars)"),
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
    app.add_handler(CallbackQueryHandler(on_preset_callback, pattern=r"^comp_preset:"))
    app.add_handler(CallbackQueryHandler(on_vpose_callback, pattern=r"^comp_vpose:"))
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
