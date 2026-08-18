"""
FAQ / consumer secretary bot (Telegram Business Chatbots + direct DMs).

- Answers questions via OpenAI (same keys as dashboard: TBCC_OPENAI_API_KEY).
- Points packs and checkout to the payment bot (TBCC_PAYMENT_BOT_USERNAME / BOT_USERNAME).
- Optional: Telegram Business — replies pass through business_connection_id when present.
- Business chats default to **suggest** (draft DM’d to you); set TBCC_SECRETARY_AUTO_REPLY=1 for in-thread auto-reply.

Run: cd tbcc/backend && python -m bots.secretary_bot

Env: TBCC_SECRETARY_BOT_TOKEN (or SECRETARY_BOT_TOKEN), TBCC_API_URL, TBCC_OPENAI_API_KEY, ADMIN_TELEGRAM_ID (for drafts + admin inbox)
Admin inbox (payment, loot, ops): /inbox /now /payment /loot /ops /critical /read /status — see TBCC_INBOX_* in .env.example
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
import re
import secrets
import sys
import time
from collections import deque
from pathlib import Path

_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from dotenv import load_dotenv

import httpx

_env = Path(__file__).resolve().parent.parent.parent / ".env"
if _env.exists():
    load_dotenv(_env, override=True)

from telegram import (
    BotCommand,
    BotCommandScopeChat,
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonCommands,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction
from telegram.error import NetworkError, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bots.error_reporter import report_bot_error
from bots.zeus_menu import (
    admin_inbox_submenu_keyboard as _admin_inbox_submenu_keyboard,
    admin_main_menu_keyboard as _admin_main_menu_keyboard,
    admin_more_submenu_keyboard as _admin_more_submenu_keyboard,
    admin_ops_submenu_keyboard as _admin_ops_submenu_keyboard,
    format_stack_status_html,
    network_submenu_keyboard as _network_submenu_keyboard,
    normalize_menu_callback,
    payment_bot_username as _payment_bot_username,
    payment_inline_keyboard as _payment_inline_keyboard,
    user_main_menu_keyboard as _user_main_menu_keyboard,
)

from app.services.format_engine import (
    apply_llm_derived_emotion_for_user,
    finalize_assistant_turn,
    finalize_assistant_turn_for_user,
    format_engine_enabled,
    get_context_display,
    get_user_context_public_summary,
    list_recent_contexts,
    load_recent_messages_for_llm,
    prepare_user_turn,
    record_external_assistant_turn,
    record_dropped_turn,
)
from app.services.secretary_rag import build_rag_context_suffix
from app.services.secretary_reply_mode import get_reply_mode, mode_label, set_reply_mode
from app.services.secretary_sales_coach import build_sales_coach_suffix
from app.services.secretary_intent import classify_intent, intent_label
from app.services.secretary_behavior import (
    apply_symmetry,
    behavior_suffix,
    corpus_candidates,
)
from app.services.secretary_drafts import (
    append_triage_instruction,
    build_redo_suffix,
    count_drafts,
    delete_draft,
    get_draft,
    list_drafts,
    parse_triage_candidates,
    parse_triage_emotion,
    apply_candidate_symmetry,
    pick_candidate,
    resolve_variant,
    save_draft,
    suggest_customer_lines,
    update_draft_reply,
)
from app.database.session import SessionLocal
from app.models.secretary_knowledge import SecretaryKnowledgeEntry
from app.models.secretary_user_context import SecretaryUserContext
from app.services.secretary_settings_effective import get_effective_secretary_settings
from app.services.admin_inbox import (
    admin_telegram_ids,
    format_inbox_digest,
    get_inbox_event_by_id,
    get_last_read_ts,
    inbox_enabled,
    list_inbox_events,
    mark_inbox_read,
    parse_admin_telegram_id,
    push_admin_inbox_event,
)
from app.services.cursor_triage import run_cursor_triage, triage_enabled, triage_usage_today
from app.services.focus_profile import apply_focus_profile, get_focus_state, lock_events_recent_count
from app.services.ops_flywheel import approve_action, flywheel_status, list_pending, reject_action
from app.services.ops_triage_bundle import build_triage_bundle, tail_error_hub
from app.services.secretary_llm_config import (
    apply_env_llm_preset,
    apply_openrouter_preset,
    clear_llm_api_key_override,
    clear_llm_base_url_override,
    env_llm_preset_catalog,
    persist_llm_api_key,
    persist_llm_base_url,
    persist_llm_model,
    secretary_llm_configured,
    secretary_llm_status,
    probe_secretary_llm,
)
from app.services.secretary_llm import (
    append_auto_emotion_instruction,
    complete_secretary_chat,
    default_system_prompt,
    extract_emotion_block,
    fetch_subscription_catalog_snippet,
    persist_system_prompt,
    resolve_system_prompt,
)
from app.services.secretary_affiliate_intake import (
    intake_affiliate_sponsor,
    parse_affiliate_intake_args,
    parse_affiliate_intake_text,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

API_BASE = (os.getenv("TBCC_SECRETARY_API_URL") or os.getenv("TBCC_API_URL") or "http://127.0.0.1:8000").rstrip("/")

# (user_id, deque of monotonic timestamps)
_rate_log: dict[int, deque[float]] = {}
_business_msg_seen: dict[str, float] = {}
# message_id → unix time of our own business send (Pilot approve / Auto _reply echo-dedupe)
_sent_business_msg_ids: dict[int, float] = {}
_SENT_BUSINESS_MSG_TTL_S = 120.0


def _save_draft(**kwargs: object) -> dict:
    with SessionLocal() as db:
        return save_draft(db, **kwargs)  # type: ignore[arg-type]


def _load_draft(draft_id: str) -> dict | None:
    with SessionLocal() as db:
        return get_draft(db, draft_id)


def _update_draft_reply(draft_id: str, reply: str, candidates: dict | None = None) -> dict | None:
    with SessionLocal() as db:
        return update_draft_reply(db, draft_id, reply, candidates=candidates)


def _drop_draft(draft_id: str) -> bool:
    with SessionLocal() as db:
        return delete_draft(db, draft_id)


async def _reject_draft_recording_drop(draft_id: str) -> bool:
    """Drop a Pilot draft; count it as a silent FE closure before delete (Gap G7)."""
    item = await asyncio.to_thread(_load_draft, draft_id)
    uid = int((item or {}).get("user_id") or 0) if item else 0
    if uid:
        try:
            await asyncio.to_thread(record_dropped_turn, uid)
        except Exception:
            logger.warning("format_engine record_dropped_turn failed uid=%s", uid, exc_info=True)
    return await asyncio.to_thread(_drop_draft, draft_id)


def _list_pending_drafts(limit: int = 20) -> list[dict]:
    with SessionLocal() as db:
        return list_drafts(db, limit=limit)


def _secretary_token() -> str:
    return (os.getenv("TBCC_SECRETARY_BOT_TOKEN") or os.getenv("SECRETARY_BOT_TOKEN") or "").strip()


def _rate_limit_per_minute() -> int:
    """Cap assistant + command traffic per user per rolling minute (abuse / cost control)."""
    raw = (os.getenv("TBCC_SECRETARY_RATE_LIMIT_PER_MIN") or "12").strip()
    try:
        return max(1, min(120, int(raw)))
    except ValueError:
        return 12


def _history_max_messages() -> int:
    raw = (os.getenv("TBCC_SECRETARY_HISTORY_MAX_MESSAGES") or "12").strip()
    try:
        return max(2, min(24, int(raw)))
    except ValueError:
        return 12


def _admin_user_id() -> int | None:
    return parse_admin_telegram_id()


def _admin_user_id_set() -> set[int]:
    return admin_telegram_ids()


def enforce_brevity(text: str) -> str:
    """Cap Auto-mode replies at two sentences / 350 chars. No outbound send."""
    raw = (text or "").strip()
    if not raw:
        return raw
    if not re.search(r"[.?!]", raw):
        return raw[:350] + "…" if len(raw) > 350 else raw
    parts = [p.strip() for p in re.split(r"(?<=[.?!])\s+", raw) if p.strip()]
    joined = " ".join(parts[:2]).strip() if parts else raw
    if len(joined) > 350:
        return joined[:350] + "…"
    return joined


def _allow_rate_limit(user_id: int) -> bool:
    if user_id in _admin_user_id_set():
        return True
    cap = _rate_limit_per_minute()
    window = 60.0
    now = time.monotonic()
    dq = _rate_log.setdefault(user_id, deque())
    while dq and now - dq[0] > window:
        dq.popleft()
    if len(dq) >= cap:
        return False
    dq.append(now)
    return True


async def _reply(
    message,
    text: str,
    context: ContextTypes.DEFAULT_TYPE,
    **kwargs,
) -> None:
    """Business chats need bot.send_message — Message.reply_text rejects business_connection_id."""
    bc = getattr(message, "business_connection_id", None)
    if bc is not None:
        sent = await context.bot.send_message(
            chat_id=message.chat_id,
            text=text,
            business_connection_id=str(bc),
            reply_to_message_id=message.message_id,
            **kwargs,
        )
        _remember_sent_business_msg(getattr(sent, "message_id", None))
        return
    await message.reply_text(text, **kwargs)


async def _send_chat_action(message, context: ContextTypes.DEFAULT_TYPE, action: ChatAction) -> None:
    bc = getattr(message, "business_connection_id", None)
    if bc is not None:
        await context.bot.send_chat_action(
            chat_id=message.chat_id,
            action=action,
            business_connection_id=str(bc),
        )
        return
    await context.bot.send_chat_action(chat_id=message.chat_id, action=action)


HISTORY_KEY = "secretary_history"
BIZ_LINES_KEY = "secretary_biz_customer_lines"
PENDING_SYSPROMPT_KEY = "pending_set_sysprompt"
PENDING_LLM_API_KEY = "pending_llm_api_key"
PENDING_LLM_BASE_URL = "pending_llm_base_url"
PENDING_LLM_MODEL = "pending_llm_model"
PENDING_AFFILIATE_LINK = "pending_affiliate_sponsor_link"

# Reply keyboard labels → handler key
_FAQ_KEYBOARD: dict[str, str] = {
    "⭐ Subscribe (payment bot)": "subscribe",
    "🛒 Shop / packs": "shop",
    "🔄 Clear FAQ context": "reset",
    "ℹ️ My support status": "mystatus",
}


def _faq_reply_keyboard() -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(label)] for label in _FAQ_KEYBOARD]
    rows.append([KeyboardButton("💬 Type your question below")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


def _format_toast_budget_text(settings: dict) -> str:
    cap = int(settings.get("max_toasts_per_2min") or 0)
    window = int(settings.get("window_seconds") or 120)
    if cap <= 0:
        budget = "<b>Off</b> — no non-payment desktop toasts"
    elif cap == 1:
        budget = f"<b>Quiet</b> — max <b>1</b> toast per {window}s"
    else:
        budget = f"<b>{cap}</b> toasts max per {window}s (~every {max(30, window // cap)}s)"
    hub = "on" if settings.get("hub_toast") else "off"
    ops = "on" if settings.get("ops_toast") else "off"
    return (
        "🔔 <b>Desktop toast budget</b>\n\n"
        f"{budget}\n"
        "<i>Payment / checkout toasts are always instant.</i>\n\n"
        f"Error-hub toasts: <code>{hub}</code> · Ops toasts: <code>{ops}</code>\n"
        "Use <b>− / +</b> or presets below. <b>Skip backlog</b> clears pending catch-up pings."
    )


def _admin_toast_submenu_keyboard(cap: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("−", callback_data="sec:menu:toast:down"),
                InlineKeyboardButton(f"Now: {cap}/2min", callback_data="sec:menu:toast:show"),
                InlineKeyboardButton("+", callback_data="sec:menu:toast:up"),
            ],
            [
                InlineKeyboardButton("Off (0)", callback_data="sec:menu:toast:set:0"),
                InlineKeyboardButton("Quiet (1)", callback_data="sec:menu:toast:set:1"),
            ],
            [
                InlineKeyboardButton("Normal (3)", callback_data="sec:menu:toast:set:3"),
                InlineKeyboardButton("Busy (5)", callback_data="sec:menu:toast:set:5"),
            ],
            [InlineKeyboardButton("🔕 Skip backlog", callback_data="sec:menu:run:skipbacklog")],
            [InlineKeyboardButton("◀ Ops menu", callback_data="zeus:ops:home")],
        ]
    )


async def _reply_with_keyboards(
    msg,
    text: str,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    parse_mode: str = "HTML",
) -> None:
    kwargs = {"parse_mode": parse_mode, "disable_web_page_preview": True}
    markup_inline = _payment_inline_keyboard()
    if markup_inline:
        kwargs["reply_markup"] = markup_inline
    await _reply(msg, text, context, **kwargs)
    try:
        await _reply(
            msg,
            "Quick actions:",
            context,
            reply_markup=_faq_reply_keyboard(),
        )
    except Exception as e:
        logger.debug("faq reply keyboard: %s", e)


def _auto_reply_in_business() -> bool:
    """When True, Business-connected customer chats get bot replies in-thread. Default False = suggest-only."""
    return os.getenv("TBCC_SECRETARY_AUTO_REPLY", "").strip().lower() in ("1", "true", "yes", "on")


def _suggest_for_direct_dms() -> bool:
    """When True, non-admin direct DMs to @aof_secretary_bot use draft→approve flow (Format Engine)."""
    raw = (os.getenv("TBCC_SECRETARY_SUGGEST_DIRECT") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _draft_notify_chat_ids() -> list[int]:
    """All admin chats that receive secretary draft cards."""
    ids = set(_admin_user_id_set())
    notify = _admin_notify_chat_id()
    if notify is not None:
        ids.add(int(notify))
    return sorted(ids)


def _admin_notify_chat_id() -> int | None:
    """Where to send draft replies in suggest mode (defaults to ADMIN_TELEGRAM_ID)."""
    raw = (os.getenv("TBCC_SECRETARY_SUGGEST_NOTIFY_CHAT_ID") or os.getenv("ADMIN_TELEGRAM_ID") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _can_manage_drafts(update: Update) -> bool:
    """Allow draft/inbox actions from configured admin user(s) or notify chat."""
    user = update.effective_user
    chat = update.effective_chat
    admin_ids = _admin_user_id_set()
    if user and user.id in admin_ids:
        return True
    if chat and chat.id in admin_ids:
        return True
    return False


def _is_owner_message(user_id: int) -> bool:
    return user_id in _admin_user_id_set()


async def _reply_inbox_denied(msg, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _admin_user_id_set():
        await _reply(
            msg,
            "Admin inbox is not configured on the server (check <code>ADMIN_TELEGRAM_ID</code> in tbcc/.env).",
            context,
            parse_mode="HTML",
        )
        return
    await _reply(
        msg,
        "Admin only — your Telegram user id must match <code>ADMIN_TELEGRAM_ID</code> "
        "(or <code>TBCC_ALBUM_COMPOSER_EXTRA_ADMIN_IDS</code>).",
        context,
        parse_mode="HTML",
    )


def _business_msg_dedupe_key(bc_id: str, user_id: int, message_id: int) -> str:
    return f"{bc_id}:{user_id}:{message_id}"


def _already_processed_business_msg(bc_id: str, user_id: int, message_id: int) -> bool:
    key = _business_msg_dedupe_key(bc_id, user_id, message_id)
    now = time.monotonic()
    prev = _business_msg_seen.get(key)
    if prev is not None and now - prev < 45.0:
        return True
    _business_msg_seen[key] = now
    if len(_business_msg_seen) > 500:
        cutoff = now - 120.0
        for k, t in list(_business_msg_seen.items()):
            if t < cutoff:
                _business_msg_seen.pop(k, None)
    return False


def _prune_sent_business_msg_ids(now: float | None = None) -> None:
    stamp = now if now is not None else time.time()
    cutoff = stamp - _SENT_BUSINESS_MSG_TTL_S
    for mid, ts in list(_sent_business_msg_ids.items()):
        if ts < cutoff:
            _sent_business_msg_ids.pop(mid, None)


def _remember_sent_business_msg(message_id: int | None) -> None:
    if message_id is None:
        return
    now = time.time()
    _sent_business_msg_ids[int(message_id)] = now
    _prune_sent_business_msg_ids(now)


async def _prune_sent_business_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    _prune_sent_business_msg_ids()


def _customer_reply_mode(user_id: int, *, is_business: bool) -> str:
    with SessionLocal() as db:
        return get_reply_mode(db, int(user_id), is_business=is_business)


def _draft_keyboard(
    draft_id: str,
    reply_plain: str,
    *,
    user_id: int,
    reply_mode: str = "pilot",
    candidates: dict | None = None,
) -> InlineKeyboardMarkup:
    cands = candidates if isinstance(candidates, dict) else {}
    copy_src = str(cands.get("natural") or reply_plain)
    copy_text = copy_src[:256] if len(copy_src) > 256 else copy_src
    row0: list[InlineKeyboardButton] = [
        InlineKeyboardButton("Send N", callback_data=f"sec:ap:{draft_id}:n"),
        InlineKeyboardButton("Send C", callback_data=f"sec:ap:{draft_id}:k"),
        InlineKeyboardButton("Send X", callback_data=f"sec:ap:{draft_id}:x"),
        InlineKeyboardButton("Drop", callback_data=f"sec:rj:{draft_id}"),
    ]
    try:
        row0.insert(
            0,
            InlineKeyboardButton("Copy N", copy_text=CopyTextButton(text=copy_text)),
        )
    except TypeError:
        pass
    row1 = [
        InlineKeyboardButton("↻ Pro", callback_data=f"sec:rd:{draft_id}:pro"),
        InlineKeyboardButton("↻ Casual", callback_data=f"sec:rd:{draft_id}:casual"),
        InlineKeyboardButton("↻ Short", callback_data=f"sec:rd:{draft_id}:short"),
    ]
    pilot_mark = "·" if str(reply_mode).lower() == "pilot" else ""
    auto_mark = "·" if str(reply_mode).lower() == "auto" else ""
    row2 = [
        InlineKeyboardButton(
            f"Pilot{pilot_mark}",
            callback_data=f"sec:mode:pilot:{int(user_id)}",
        ),
        InlineKeyboardButton(
            f"Auto{auto_mark}",
            callback_data=f"sec:mode:auto:{int(user_id)}",
        ),
    ]
    return InlineKeyboardMarkup([row0, row1, row2])


def _format_draft_card(
    draft_id: str,
    *,
    who: str,
    user_id: int,
    customer_line: str,
    reply_plain: str,
    reply_mode: str = "pilot",
    coach_hint: str = "",
    candidates: dict | None = None,
) -> str:
    who_disp = f"@{html.escape(who)}" if who and who != "no_username" else "no @"
    cust = html.escape(customer_line[:400])
    mode = html.escape(mode_label(reply_mode))
    coach_line = ""
    if coach_hint:
        coach_line = f"Coach: <i>{html.escape(coach_hint[:120])}</i>\n"
    cands = candidates if isinstance(candidates, dict) else {}
    n = html.escape(str(cands.get("natural") or reply_plain)[:400])
    k = html.escape(str(cands.get("clear") or "")[:400])
    x = html.escape(str(cands.get("close") or "")[:400])
    body_replies = f"<b>N</b> natural\n<pre>{n}</pre>\n"
    if k:
        body_replies += f"<b>C</b> clear\n<pre>{k}</pre>\n"
    if x:
        body_replies += f"<b>X</b> close\n<pre>{x}</pre>"
    if not k and not x:
        body_replies = f"<pre>{html.escape(reply_plain[:2800])}</pre>"
    return (
        f"<b>{draft_id}</b> · {who_disp} · <code>{user_id}</code>\n"
        f"Mode: <b>{mode}</b> · next turns use this until you toggle\n"
        f"{coach_line}"
        f"In: {cust}\n\n"
        f"{body_replies}"
    )


async def _send_draft_to_admin(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    draft_id: str,
    who: str,
    user_id: int,
    customer_line: str,
    reply_plain: str,
    reply_mode: str = "pilot",
    coach_hint: str = "",
    candidates: dict | None = None,
) -> None:
    targets = _draft_notify_chat_ids()
    if not targets:
        return
    body = _format_draft_card(
        draft_id,
        who=who,
        user_id=user_id,
        customer_line=customer_line,
        reply_plain=reply_plain,
        reply_mode=reply_mode,
        coach_hint=coach_hint,
        candidates=candidates,
    )
    markup = _draft_keyboard(
        draft_id, reply_plain, user_id=user_id, reply_mode=reply_mode, candidates=candidates
    )
    for admin_id in targets:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=body,
                parse_mode="HTML",
                reply_markup=markup,
            )
        except Exception as e:
            logger.warning("secretary: could not DM admin %s draft %s: %s", admin_id, draft_id, e)


async def _deliver_draft_to_customer(
    context: ContextTypes.DEFAULT_TYPE, draft_id: str, *, variant: str | None = None
) -> tuple[bool, str]:
    item = await asyncio.to_thread(_load_draft, draft_id)
    if not item:
        return False, f"Draft {draft_id} not found."
    chat_id = int(item["chat_id"])
    bc_id = item.get("business_connection_id")
    text = pick_candidate(item, variant)
    if not text:
        text = str(item.get("reply") or "")[:4096]
    try:
        if bc_id:
            sent = await context.bot.send_message(
                chat_id=chat_id, text=text[:4096], business_connection_id=str(bc_id)
            )
            _remember_sent_business_msg(getattr(sent, "message_id", None))
        else:
            await context.bot.send_message(chat_id=chat_id, text=text[:4096])
    except TypeError:
        await context.bot.send_message(chat_id=chat_id, text=text[:4096])
    except Exception as e:
        logger.exception("approve failed draft=%s chat=%s bc=%s: %s", draft_id, chat_id, bc_id, e)
        return False, f"Could not send: {e}"
    user_id = int(item.get("user_id") or 0)
    if user_id and format_engine_enabled():
        try:
            finalize_assistant_turn_for_user(user_id, text)
        except Exception as e:
            logger.warning("format_engine draft finalize uid=%s: %s", user_id, e)
        try:
            _schedule_format_live(context, user_id)
        except Exception:
            logger.debug("format live refresh after draft send failed", exc_info=True)
    await asyncio.to_thread(_drop_draft, draft_id)
    label = resolve_variant(variant)
    return True, f"Sent {draft_id} ({label})."


async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    if not _can_manage_drafts(update):
        await msg.reply_text("Only the configured admin can approve drafts here.")
        return
    if not context.args:
        await msg.reply_text("Usage: /approve <draft_id> [n|c|x]")
        return
    draft_id = str(context.args[0]).strip().upper()
    variant = str(context.args[1]).strip() if len(context.args) > 1 else "n"
    ok, detail = await _deliver_draft_to_customer(context, draft_id, variant=variant)
    await msg.reply_text(detail)


async def cmd_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    if not _can_manage_drafts(update):
        await msg.reply_text("Only the configured admin can reject drafts here.")
        return
    if not context.args:
        await msg.reply_text("Usage: /reject <draft_id>")
        return
    draft_id = str(context.args[0]).strip().upper()
    removed = await _reject_draft_recording_drop(draft_id)
    if removed:
        await msg.reply_text(f"Rejected draft {draft_id}.")
    else:
        await msg.reply_text(f"Draft {draft_id} not found.")


async def cmd_redo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    if not _can_manage_drafts(update):
        await msg.reply_text("Admin only.")
        return
    if not context.args:
        await msg.reply_text("Usage: /redo <draft_id> [pro|casual|short|custom …instruction…]")
        return
    if not secretary_llm_configured():
        await msg.reply_text("OpenAI not configured.")
        return
    draft_id = str(context.args[0]).strip().upper()
    item = await asyncio.to_thread(_load_draft, draft_id)
    if not item:
        await msg.reply_text(f"Draft {draft_id} not found.")
        return
    style = (context.args[1].strip().lower() if len(context.args) > 1 else "pro")
    custom = " ".join(context.args[2:]).strip() if len(context.args) > 2 else ""
    llm_messages = item.get("llm_messages")
    if not isinstance(llm_messages, list) or not llm_messages:
        await msg.reply_text("No LLM context stored for this draft — reject and wait for a new customer message.")
        return
    suffix = build_redo_suffix(str(item.get("extra_system_suffix") or ""), style, custom)
    try:
        reply = await complete_secretary_chat(llm_messages, extra_system_suffix=suffix)
    except Exception as e:
        await msg.reply_text(f"Redo failed: {e}")
        return
    emotion_block = parse_triage_emotion(reply)
    uid = int(item.get("user_id") or 0)
    if emotion_block and uid:
        try:
            await asyncio.to_thread(apply_llm_derived_emotion_for_user, uid, emotion_block)
        except Exception:
            logger.debug("secretary redo emotion ingest failed uid=%s", uid, exc_info=True)
    cands = parse_triage_candidates(reply)
    natural = cands["natural"]
    await asyncio.to_thread(_update_draft_reply, draft_id, natural, cands)
    who = str(item.get("who") or "no_username")
    uid = int(item.get("user_id") or 0)
    cust = str(item.get("customer_preview") or "")
    is_biz = bool(item.get("business_connection_id"))
    rmode = _customer_reply_mode(uid, is_business=is_biz) if uid else "pilot"
    await _send_draft_to_admin(
        context,
        draft_id=draft_id,
        who=who,
        user_id=uid,
        customer_line=cust,
        reply_plain=natural,
        reply_mode=rmode,
        coach_hint=str(item.get("coach_hint") or ""),
        candidates=cands,
    )
    await msg.reply_text(f"↻ {draft_id} — new suggestion above.")


async def on_draft_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    if not _can_manage_drafts(update):
        await query.answer("Admin only.", show_alert=True)
        return
    parts = query.data.split(":")
    if len(parts) < 3 or parts[0] != "sec":
        return
    action = parts[1]

    if action == "mode" and len(parts) >= 4:
        mode = parts[2].lower()
        try:
            uid = int(parts[3])
        except ValueError:
            await query.answer("Bad user id", show_alert=True)
            return
        if mode not in ("pilot", "auto"):
            await query.answer("Bad mode", show_alert=True)
            return
        try:
            with SessionLocal() as db:
                set_reply_mode(db, uid, mode)
        except Exception as e:
            await query.answer(f"Save failed: {e}", show_alert=True)
            return
        label = mode_label(mode)
        await query.answer(f"Mode → {label}")
        try:
            _schedule_format_live(context, uid)
        except Exception:
            logger.debug("format live refresh after mode toggle failed", exc_info=True)
        if query.message:
            note = (
                f"Mode for <code>{uid}</code> set to <b>{html.escape(label)}</b>. "
                "Current draft is unchanged — tap ✓ Send if you still want this reply. "
                "Later turns follow the new mode."
            )
            try:
                await query.message.reply_text(note, parse_mode="HTML")
            except Exception:
                await query.message.reply_text(f"Mode for {uid} → {label}")
        return

    draft_id = parts[2].upper()
    await query.answer()
    if action == "ap":
        variant = parts[3] if len(parts) >= 4 else "n"
        ok, detail = await _deliver_draft_to_customer(context, draft_id, variant=variant)
        if query.message:
            await query.message.reply_text(detail)
        return
    if action == "rj":
        removed = await _reject_draft_recording_drop(draft_id)
        if removed and query.message:
            await query.message.reply_text(f"Dropped {draft_id}.")
        return
    if action == "rd" and len(parts) >= 4:
        style = parts[3].lower()
        item = await asyncio.to_thread(_load_draft, draft_id)
        if not item or not isinstance(item.get("llm_messages"), list) or not item.get("llm_messages"):
            await query.answer("Draft expired.", show_alert=True)
            return
        suffix = build_redo_suffix(str(item.get("extra_system_suffix") or ""), style, "")
        try:
            reply = await complete_secretary_chat(item["llm_messages"], extra_system_suffix=suffix)
        except Exception as e:
            await query.answer(f"Redo failed: {e}", show_alert=True)
            return
        emotion_block = parse_triage_emotion(reply)
        uid = int(item.get("user_id") or 0)
        if emotion_block and uid:
            try:
                await asyncio.to_thread(apply_llm_derived_emotion_for_user, uid, emotion_block)
            except Exception:
                logger.debug("secretary redo emotion ingest failed uid=%s", uid, exc_info=True)
        cands = parse_triage_candidates(reply)
        natural = cands["natural"]
        await asyncio.to_thread(_update_draft_reply, draft_id, natural, cands)
        who = str(item.get("who") or "no_username")
        uid = int(item.get("user_id") or 0)
        cust = str(item.get("customer_preview") or "")
        is_biz = bool(item.get("business_connection_id"))
        rmode = _customer_reply_mode(uid, is_business=is_biz) if uid else "pilot"
        await _send_draft_to_admin(
            context,
            draft_id=draft_id,
            who=who,
            user_id=uid,
            customer_line=cust,
            reply_plain=natural,
            reply_mode=rmode,
            coach_hint=str(item.get("coach_hint") or ""),
            candidates=cands,
        )
        if query.message:
            await query.message.reply_text(f"↻ {draft_id} ({style})")


async def cmd_drafts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    if not _can_manage_drafts(update):
        await msg.reply_text("Only the configured admin can view pending drafts here.")
        return
    items = await asyncio.to_thread(_list_pending_drafts, 20)
    if not items:
        await msg.reply_text("No pending drafts.")
        return
    lines = ["<b>Pending drafts</b>"]
    for item in items:
        did = html.escape(str(item.get("draft_id") or ""))
        who = html.escape(str(item.get("who") or "unknown"))
        uid = html.escape(str(item.get("user_id") or ""))
        lines.append(f"• <code>{did}</code> — @{who} id <code>{uid}</code>")
    lines.append("\nUse <code>/approve DRAFT_ID</code> or <code>/reject DRAFT_ID</code>.")
    await msg.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_as_customer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: dry-run Format Engine draft flow without a second Telegram account."""
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await msg.reply_text("Admin only.")
        return
    if not context.args:
        await msg.reply_text(
            "Usage: <code>/as_customer</code> &lt;message&gt;\n"
            "Simulates a non-admin customer DM — you get a draft card, nothing is sent to anyone else.",
            parse_mode="HTML",
        )
        return
    fake_text = " ".join(context.args).strip()
    if not fake_text:
        return
    # Reuse suggest pipeline with a synthetic customer id (negative = never real user).
    sim_uid = int(context.user_data.get("simulate_customer_uid") or -9_000_001_234)
    context.user_data["simulate_customer_uid"] = sim_uid - 1
    from types import SimpleNamespace

    fake_user = SimpleNamespace(id=sim_uid, username="simulate_customer")
    fake_msg = SimpleNamespace(
        chat_id=msg.chat_id,
        text=fake_text,
        chat=msg.chat,
        message_id=None,
        business_connection_id=None,
    )
    fake_update = SimpleNamespace(
        effective_message=fake_msg,
        effective_user=fake_user,
    )
    await on_private_text(fake_update, context)
    await msg.reply_text(
        f"Simulated customer uid <code>{sim_uid}</code> — check draft DM above.",
        parse_mode="HTML",
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if not _allow_rate_limit(user.id):
        await _reply(
            msg,
            "You are sending requests a bit fast. This assistant is <b>rate-limited</b> per minute — "
            "please wait up to a minute, then try <b>/start</b> or your question again.",
            context,
            parse_mode="HTML",
        )
        return
    pay = _payment_bot_username()
    pay_safe = html.escape(pay) if pay else ""
    pay_block = (
        "<b>Where to buy (checkout only in the payment bot)</b>\n"
        f"Subscriptions, Stars invoices, and digital packs all run in our official payment bot — not in this chat:\n"
        f"@{pay_safe}\n"
        "Open that chat and send <b>/subscribe</b> for membership tiers, <b>/packs</b> for digital packs, "
        "or <b>/shop</b> for the full storefront and promos."
        if pay
        else "<b>Checkout</b>\nPurchases run through the main payment bot — ask an admin for the link."
    )
    biz_note = ""
    if getattr(msg, "business_connection_id", None) is not None and not _auto_reply_in_business():
        biz_note = (
            "\n\n<b>Linked business chats:</b> by default I <b>draft</b> replies to your admin DM — "
            "I don't post to the customer until you set <code>TBCC_SECRETARY_AUTO_REPLY=1</code> on the server."
        )
    text = (
        "Welcome — you are talking to the <b>AOF assistant</b>.\n\n"
        "<b>What AOF is (high level)</b>\n"
        "AOF is a premium adult brand built around curated access: member experiences, subscription tiers, "
        "and digital packs when you want something specific. This chat is your <b>FAQ lane</b> — no payments "
        "or invoices happen here.\n\n"
        "<b>What to ask here</b>\n"
        "• How access, renewals, and channel membership generally work\n"
        "• How subscription tiers differ and what to expect before you buy\n"
        "• Questions about the catalog at a high level (I can summarize what our API exposes about plans)\n"
        "• Anything unclear before you move to checkout — I will steer you to the right command in the payment bot\n\n"
        + pay_block
        + "\n\n<b>Fair use</b>\n"
        "Messages (including <b>/start</b>, <b>/help</b>, and plain-text questions) share a <b>strict per-minute rate limit</b> "
        "so abuse cannot burn the service down. Ask a real question when you are ready; with the backend online I also "
        "pull short live snippets of active subscription plans to ground answers about Stars and durations."
        + "\n\n<b>Commands</b>\n"
        "/mystatus — see your FAQ thread phase\n"
        "/reset — clear remembered context\n"
        "Use the keyboard below for shortcuts."
        + biz_note
    )
    if _can_manage_drafts(update):
        text += (
            f"\n\n<b>Admin</b> — uid <code>{user.id}</code> recognized. "
            "Tap <b>Menu</b> below or send <code>/commands</code> for the full list.\n"
            "<i>Format Engine drafts only fire for <b>non-admin</b> customer DMs — "
            "test with a fourth account or ask a friend to message this bot.</i>"
        )
    menu_kb = _admin_main_menu_keyboard() if _can_manage_drafts(update) else _user_main_menu_keyboard()
    await _reply(msg, text, context, parse_mode="HTML", disable_web_page_preview=True, reply_markup=menu_kb)
    if not _can_manage_drafts(update):
        try:
            await _reply(
                msg,
                "Quick actions:",
                context,
                reply_markup=_faq_reply_keyboard(),
            )
        except Exception as e:
            logger.debug("faq reply keyboard: %s", e)


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Zeus Phase 1 hub — Network | Inbox | Ops | More (admin); deep links for users."""
    msg = update.effective_message
    if not msg:
        return
    if _can_manage_drafts(update):
        await _reply(
            msg,
            "⚡ <b>TBCC Zeus — main menu</b>\n\n"
            "<b>Network</b> — shop, loot, companion deep links\n"
            "<b>Inbox</b> — payment / loot / ops digests\n"
            "<b>Ops</b> — stack status, relief, flywheel, toasts\n"
            "<b>More</b> — FAQ, LLM config, commands\n\n"
            "<i>Legacy <code>sec:menu:</code> callbacks still work.</i>",
            context,
            parse_mode="HTML",
            reply_markup=_admin_main_menu_keyboard(),
        )
        return
    await _reply(
        msg,
        "🏠 <b>Menu</b>\n"
        "Shop, Loot Room, and FAQ shortcuts.",
        context,
        parse_mode="HTML",
        reply_markup=_user_main_menu_keyboard(),
    )


async def cmd_mystatus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if not format_engine_enabled():
        await _reply(
            msg,
            "Personalized context tracking is off on the server. You can still ask FAQ questions anytime.",
            context,
        )
        return
    summary = await asyncio.to_thread(get_user_context_public_summary, user.id)
    if not summary:
        await _reply(
            msg,
            "No saved context yet for this chat — send a question and I'll remember the thread for better answers.",
            context,
        )
        return
    phase = html.escape(str(summary.get("phase") or "introduction"))
    mc = int(summary.get("message_count") or 0)
    emo = html.escape(str(summary.get("emotional_summary") or "—"))
    lines = [
        "<b>Your FAQ thread</b>",
        f"Support phase: <code>{phase}</code>",
        f"Messages in thread: <b>{mc}</b>",
        f"Summary: {emo}",
        "\nUse <b>/reset</b> or the keyboard button to clear context.",
    ]
    await _reply(msg, "\n".join(lines), context, parse_mode="HTML")


def _chunk_plain_text(text: str, *, max_len: int = 3800) -> list[str]:
    body = (text or "").strip()
    if not body:
        return ["(empty)"]
    if len(body) <= max_len:
        return [body]
    chunks: list[str] = []
    start = 0
    while start < len(body):
        chunks.append(body[start : start + max_len])
        start += max_len
    return chunks


async def _reply_preformatted_chunks(
    msg,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    header: str,
    body: str,
) -> None:
    await _reply(msg, header, context, parse_mode="HTML")
    parts = _chunk_plain_text(body)
    for i, chunk in enumerate(parts, start=1):
        suffix = f" <i>({i}/{len(parts)})</i>" if len(parts) > 1 else ""
        await _reply(
            msg,
            f"<pre>{html.escape(chunk)}</pre>{suffix}",
            context,
            parse_mode="HTML",
        )


async def cmd_sysprompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: show effective system prompt."""
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return

    def _load() -> dict:
        prompt, source = resolve_system_prompt()
        eff = get_effective_secretary_settings()
        extra = (eff.get("system_prompt_extra") or "").strip()
        return {
            "prompt": prompt,
            "source": source,
            "chars": len(prompt),
            "extra": extra,
            "extra_chars": len(extra),
        }

    data = await asyncio.to_thread(_load)
    extra_line = ""
    if data["extra"]:
        extra_line = (
            f"\nAppended extra: <b>{data['extra_chars']}</b> chars "
            "(dashboard / TBCC_SECRETARY_SYSTEM_PROMPT_EXTRA)"
        )
    header = (
        "<b>Secretary system prompt</b>\n"
        f"Source: <code>{html.escape(str(data['source']))}</code> · "
        f"<b>{data['chars']}</b> chars{extra_line}\n"
        "Edit: <code>/set_sysprompt</code> then send text, "
        "<code>/set_sysprompt your text</code>, reply to a message, or "
        "<code>/clear_sysprompt</code>"
    )
    await _reply_preformatted_chunks(msg, context, header=header, body=str(data["prompt"]))


async def cmd_set_sysprompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: set dashboard system prompt override."""
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return

    inline = " ".join(context.args or []).strip()
    reply_body = ""
    if msg.reply_to_message and msg.reply_to_message.text:
        reply_body = msg.reply_to_message.text.strip()

    new_text = inline or reply_body
    if new_text:
        try:
            result = await asyncio.to_thread(persist_system_prompt, new_text)
        except ValueError as e:
            await _reply(msg, f"Not saved: {html.escape(str(e))}", context, parse_mode="HTML")
            return
        except Exception as e:
            await _reply(msg, f"Save failed: {html.escape(str(e))}", context, parse_mode="HTML")
            return
        await _reply(
            msg,
            f"✅ System prompt saved (<code>{result['source']}</code>, {result['chars']} chars). "
            "Use <code>/sysprompt</code> to review.",
            context,
            parse_mode="HTML",
        )
        return

    context.user_data[PENDING_SYSPROMPT_KEY] = True
    await _reply(
        msg,
        "Send the <b>full system prompt</b> in your next message (plain text).\n"
        "Cancel: <code>/cancel</code>",
        context,
        parse_mode="HTML",
    )


async def cmd_clear_sysprompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: clear dashboard system prompt override."""
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return
    try:
        result = await asyncio.to_thread(persist_system_prompt, None)
    except Exception as e:
        await _reply(msg, f"Clear failed: {html.escape(str(e))}", context, parse_mode="HTML")
        return
    await _reply(
        msg,
        f"✅ Dashboard prompt cleared. Active source: <code>{html.escape(str(result['source']))}</code> "
        f"({result['chars']} chars).",
        context,
        parse_mode="HTML",
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    cancelled: list[str] = []
    if context.user_data.pop(PENDING_SYSPROMPT_KEY, None):
        cancelled.append("system prompt edit")
    if context.user_data.pop(PENDING_LLM_API_KEY, None):
        cancelled.append("API key input")
    if context.user_data.pop(PENDING_LLM_BASE_URL, None):
        cancelled.append("endpoint URL input")
    if context.user_data.pop(PENDING_LLM_MODEL, None):
        cancelled.append("model id input")
    if context.user_data.pop(PENDING_AFFILIATE_LINK, None):
        cancelled.append("sponsor link intake")
    if cancelled:
        await _reply(msg, "Cancelled: " + ", ".join(cancelled) + ".", context)
        return
    await _reply(msg, "Nothing to cancel.", context)


def _public_commands_reference() -> str:
    return (
        "<b>Public commands</b> · <u>@aof_secretary_bot</u>\n\n"
        "<b>FAQ</b>\n"
        "/start · /help — intro & menu\n"
        "/menu — inline shortcuts\n"
        "/subscribe · /shop — payment bot links\n"
        "/mystatus — Format Engine thread phase\n"
        "/reset — clear FAQ context\n\n"
        "<i>Plain text = FAQ question (if public FAQ enabled).</i>"
    )


def _admin_commands_reference() -> str:
    return (
        "<b>Admin commands</b> · <u>operator</u>\n"
        "<i>Your Telegram user id must match </i><code>ADMIN_TELEGRAM_ID</code><i>.</i>\n\n"
        "<b>Navigation</b>\n"
        "/menu — main inline menu\n"
        "/commands — this list\n"
        "/config — LLM key + endpoint (button tree)\n\n"
        "<b>Inbox</b>\n"
        "/inbox — recent feed\n"
        "/now — unread only\n"
        "/payment — payment category\n"
        "/loot — loot category\n"
        "/ops — ops category\n"
        "/critical — critical and important\n"
        "/read — mark inbox seen\n"
        "/status — inbox stats\n\n"
        "<b>Business supervise</b>\n"
        "<i>Customers never see the bot until you approve a draft.</i>\n"
        "/drafts — list pending suggestions\n"
        "/approve <code>draft_id</code>\n"
        "/reject <code>draft_id</code>\n"
        "/redo <code>draft_id</code> pro|casual|short\n"
        "<i>Draft cards: Send, Drop, Regenerate</i>\n\n"
        "<b>Format Engine and prompt</b>\n"
        "/formats — people cards (live in this DM)\n"
        "/fe_stats — contexts, RAG, phases\n"
        "/sysprompt — view system prompt\n"
        "/set_sysprompt — set via next message, inline text, or reply\n"
        "/clear_sysprompt — drop dashboard override\n"
        "/cancel — cancel pending prompt edit\n\n"
        "<b>Ops</b>\n"
        "/stack — tray stack status (N/M enabled)\n"
        "/relief — telegram_relief focus profile\n"
        "/toasts — desktop toast budget (non-payment)\n"
        "/skipbacklog — clear pending alert catch-up\n"
        "/focus — current focus profile state\n"
        "/triage — Cursor bundle (optional <code>event_id</code>)\n"
        "/flywheel — ops flywheel status\n"
        "/deposit <code>N</code> — Storage Hub subtopic → pool (admin, in-topic)\n\n"
        "<b>Revenue</b>\n"
        "/menu → More → <b>Add sponsor link</b> — paste affiliate URL; auto-circulates\n"
        "/addsponsor — same flow from command\n"
        "/sponsors — DM list of all affiliates (URL, clicks, attributed $)\n"
        "/affiliates — alias for /sponsors\n\n"
        "<b>Configuration</b>\n"
        "/config — LLM API key + endpoint URL (button tree, live test)\n"
        "TBCC API URL: <code>TBCC_API_URL</code> in tbcc/.env\n"
        "Internal API key: <code>TBCC_INTERNAL_API_KEY</code>\n"
        "Cursor triage: <code>CURSOR_API_KEY</code> + <code>TBCC_CURSOR_TRIAGE_ENABLED=1</code>\n\n"
        "<b>Notes</b>\n"
        "Sale and ops instant DMs work without this process; inbox callback buttons need it running.\n"
        "Same prompt settings as <code>/sysprompt</code> live in the dashboard Secretary panel."
    )


async def cmd_commands(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    if _can_manage_drafts(update):
        body = _public_commands_reference() + "\n\n" + _admin_commands_reference()
    else:
        body = _public_commands_reference()
    await _reply(msg, body, context, parse_mode="HTML")


def _clear_llm_pending(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(PENDING_LLM_API_KEY, None)
    context.user_data.pop(PENDING_LLM_BASE_URL, None)
    context.user_data.pop(PENDING_LLM_MODEL, None)


def _llm_config_keyboard() -> InlineKeyboardMarkup:
    env_rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for preset in env_llm_preset_catalog():
        label = preset["label"]
        if not preset.get("available"):
            label = f"{label} ✗"
        row.append(InlineKeyboardButton(label, callback_data=f"sec:llm:env:{preset['id']}"))
        if len(row) >= 2:
            env_rows.append(row)
            row = []
    if row:
        env_rows.append(row)
    return InlineKeyboardMarkup(
        [
            *env_rows,
            [InlineKeyboardButton("➕ Set API key", callback_data="sec:llm:set_key")],
            [InlineKeyboardButton("🔗 Set endpoint URL", callback_data="sec:llm:set_url")],
            [InlineKeyboardButton("🧪 Test API key", callback_data="sec:llm:test")],
            [InlineKeyboardButton("📝 Set model id", callback_data="sec:llm:set_model")],
            [
                InlineKeyboardButton("🗑 Clear API key", callback_data="sec:llm:clear_key"),
                InlineKeyboardButton("🗑 Clear URL", callback_data="sec:llm:clear_url"),
            ],
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="sec:llm:home"),
                InlineKeyboardButton("◀ Menu", callback_data="sec:menu:home"),
            ],
        ]
    )


def _format_llm_test_result(result: dict) -> str:
    if result.get("ok"):
        return (
            "✅ <b>LLM test passed</b>\n"
            f"Endpoint: <code>{html.escape(str(result.get('endpoint') or '—'))}</code>\n"
            f"Model: <code>{html.escape(str(result.get('model') or '—'))}</code>\n"
            f"Latency: <b>{int(result.get('latency_ms') or 0)}</b> ms\n"
            f"Reply: <code>{html.escape(str(result.get('reply_preview') or '—'))}</code>"
        )
    stage = html.escape(str(result.get("stage") or "error"))
    raw_msg = str(result.get("message") or "unknown error")
    if "insufficient_user_quota" in raw_msg or "quota is not enough" in raw_msg.lower():
        cq = result.get("cometapi_quota") or {}
        bal = cq.get("total_quota")
        reqs = cq.get("request_count")
        bal_line = f" Account balance: <b>${bal:.2f}</b>." if isinstance(bal, (int, float)) else ""
        req_line = f" Successful API calls so far: <b>{reqs}</b>." if isinstance(reqs, int) else ""
        msg = (
            "CometAPI rejected the call — <b>insufficient account balance</b> (not a TBCC wiring issue). "
            "Your key and <code>https://api.cometapi.com/v1</code> are correct."
            f"{bal_line}{req_line}\n\n"
            "CometAPI onboarding steps the <b>bot cannot do for you</b>:\n"
            "• Claim credits in console → <b>Account → Free Credits</b> or <b>Credits</b>\n"
            "• Complete “Successfully call API 1 time” — try the <b>Playground</b> first if balance is $0\n"
            "• Top up via Wallet (min $10) if needed\n\n"
            "Your API key already shows <b>unlimited</b> token limit — that part is fine."
        )
    else:
        msg = html.escape(raw_msg)
    lines = [
        "❌ <b>LLM test failed</b>",
        f"Stage: <code>{stage}</code>",
        f"Detail: {msg}",
    ]
    if result.get("endpoint"):
        lines.append(f"Endpoint: <code>{html.escape(str(result['endpoint']))}</code>")
    if result.get("model"):
        lines.append(f"Model: <code>{html.escape(str(result['model']))}</code>")
    if result.get("latency_ms") is not None:
        lines.append(f"Latency: <b>{int(result['latency_ms'])}</b> ms")
    return "\n".join(lines)


def _build_llm_config_text() -> str:
    st = secretary_llm_status()
    src = "dashboard / Telegram" if st.get("api_key_override") else "tbcc/.env"
    endpoint = st.get("endpoint_url") or "(not configured)"
    base = st.get("base_url") or "(provider default)"
    return (
        "🤖 <b>Secretary LLM configuration</b>\n\n"
        f"Provider: <code>{html.escape(str(st.get('provider') or 'openai'))}</code>\n"
        f"Model: <code>{html.escape(str(st.get('model') or '—'))}</code>\n"
        f"API key: <code>{html.escape(str(st.get('api_key_hint') or 'not set'))}</code> ({src})\n"
        f"Base URL: <code>{html.escape(str(base))}</code>\n"
        f"Completions: <code>{html.escape(str(endpoint))}</code>\n\n"
        "Presets: <b>Hcnsec</b> = your Model Square credits (api.hcnsec.cn); "
        "OpenRouter / OpenAI / Comet are separate wallets.\n"
        "Swap HF/gateway models with <b>Set model id</b> (must exist in Model Square).\n"
        "<code>/cancel</code> aborts a pending prompt."
    )


async def _send_llm_config_panel(
    target,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    edit: bool = False,
    extra_footer: str = "",
) -> None:
    body = _build_llm_config_text()
    if extra_footer:
        body = body + "\n\n" + extra_footer
    kb = _llm_config_keyboard()
    if edit and hasattr(target, "edit_message_text"):
        try:
            await target.edit_message_text(body, parse_mode="HTML", reply_markup=kb)
            return
        except TelegramError as e:
            logger.debug("llm panel edit failed: %s", e)
    chat_id = getattr(target, "chat_id", None) or getattr(getattr(target, "chat", None), "id", None)
    if chat_id is not None:
        await context.bot.send_message(chat_id=chat_id, text=body, parse_mode="HTML", reply_markup=kb)


async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: LLM key + endpoint configuration (inline buttons)."""
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return
    _clear_llm_pending(context)
    await _send_llm_config_panel(msg, context)


async def on_llm_config_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("sec:llm:"):
        return
    await query.answer()
    if not _can_manage_drafts(update):
        await query.answer("Admin only.", show_alert=True)
        return

    action = query.data.split(":", 2)[-1] if query.data.count(":") >= 2 else ""
    if query.data.startswith("sec:llm:prov:"):
        action = "prov:" + query.data.split(":")[-1]

    if action in ("home", "refresh"):
        _clear_llm_pending(context)
        await _send_llm_config_panel(query, context, edit=True)
        return

    if action == "set_key":
        _clear_llm_pending(context)
        context.user_data[PENDING_LLM_API_KEY] = True
        if query.message:
            await query.message.reply_text(
                "Send your <b>API key</b> in the next message (plain text).\n"
                "It will be saved and <b>live-tested</b> immediately.\n"
                "Cancel: <code>/cancel</code>",
                parse_mode="HTML",
            )
        return

    if action == "set_url":
        _clear_llm_pending(context)
        context.user_data[PENDING_LLM_BASE_URL] = True
        if query.message:
            await query.message.reply_text(
                "Send the <b>endpoint base URL</b> in the next message.\n"
                "Example: <code>https://openrouter.ai/api/v1</code>\n"
                "Example: <code>https://api.openai.com/v1</code>\n"
                "Cancel: <code>/cancel</code>",
                parse_mode="HTML",
            )
        return

    if action == "set_model":
        _clear_llm_pending(context)
        context.user_data[PENDING_LLM_MODEL] = True
        if query.message:
            await query.message.reply_text(
                "Send the <b>model id</b> in the next message.\n"
                "• Hcnsec: exact Model Square id (e.g. <code>step-3.5-flash</code>)\n"
                "• OpenRouter: slug (e.g. <code>openai/gpt-4o-mini</code>)\n"
                "Cancel: <code>/cancel</code>",
                parse_mode="HTML",
            )
        return

    if query.data.startswith("sec:llm:env:"):
        preset_id = query.data.split(":")[-1]
        try:
            preset = await asyncio.to_thread(apply_env_llm_preset, preset_id)
            hint = html.escape(str(preset.get("api_key_hint") or "not set"))
            missing = preset.get("missing_env")
            if missing:
                footer = (
                    f"<b>{html.escape(str(preset.get('preset')))}</b> preset applied, "
                    f"but <code>{html.escape(str(missing))}</code> is missing in island <code>.env</code>.\n"
                    "Tap <b>Set API key</b> or add the env var, then <b>Test API key</b>."
                )
            else:
                test = await asyncio.to_thread(probe_secretary_llm)
                footer = (
                    f"✅ <b>{html.escape(str(preset.get('preset')))}</b> env preset applied.\n"
                    f"Model: <code>{html.escape(str(preset.get('model')))}</code>\n"
                    f"Key: <code>{hint}</code> (env)\n"
                    + _format_llm_test_result(test)
                )
        except Exception as e:
            footer = f"Env preset failed: {html.escape(str(e))}"
        await _send_llm_config_panel(query, context, edit=True, extra_footer=footer)
        return

    if action.startswith("prov:"):
        prov = action.split(":", 1)[-1]
        try:
            if prov == "openrouter":
                preset = await asyncio.to_thread(apply_openrouter_preset)
                hint = html.escape(str(preset.get("api_key_hint") or "env TBCC_OPENROUTER_API_KEY"))
                footer = (
                    "OpenRouter preset applied.\n"
                    f"Model: <code>{html.escape(str(preset.get('model')))}</code>\n"
                    f"URL: <code>{html.escape(str(preset.get('base_url')))}</code>\n"
                    f"Key: <code>{hint}</code> (dashboard override cleared — uses env)\n"
                    "Tap <b>Test API key</b> to verify."
                )
            else:
                preset = await asyncio.to_thread(apply_env_llm_preset, prov)
                hint = html.escape(str(preset.get("api_key_hint") or "not set"))
                footer = (
                    f"{html.escape(prov)} env preset applied.\n"
                    f"Model: <code>{html.escape(str(preset.get('model')))}</code>\n"
                    f"Key: <code>{hint}</code>"
                )
        except Exception as e:
            footer = f"Provider update failed: {html.escape(str(e))}"
        await _send_llm_config_panel(query, context, edit=True, extra_footer=footer)
        return

    if action == "test":
        if query.message:
            await query.message.reply_text("🧪 Running live LLM test…", parse_mode="HTML")
        result = await asyncio.to_thread(probe_secretary_llm)
        footer = _format_llm_test_result(result)
        await _send_llm_config_panel(query, context, edit=False, extra_footer=footer)
        return

    if action == "clear_key":
        await asyncio.to_thread(clear_llm_api_key_override)
        await _send_llm_config_panel(query, context, edit=True, extra_footer="API key override cleared.")
        return

    if action == "clear_url":
        await asyncio.to_thread(clear_llm_base_url_override)
        await _send_llm_config_panel(query, context, edit=True, extra_footer="Endpoint URL override cleared.")
        return

    if action == "cometapi":
        preset = await asyncio.to_thread(apply_env_llm_preset, "cometapi")
        hint = html.escape(str(preset.get("api_key_hint") or "not set"))
        missing = preset.get("missing_env")
        footer = (
            "☄️ <b>CometAPI env preset applied</b>\n"
            f"URL: <code>{html.escape(str(preset.get('base_url')))}</code>\n"
            f"Provider: <code>openai</code> · Model: <code>{html.escape(str(preset.get('model')))}</code>\n"
            f"Key: <code>{hint}</code>"
        )
        if missing:
            footer += (
                f"\n\nAdd <code>{html.escape(str(missing))}</code> to island env, "
                "or tap <b>Set API key</b>, then <b>Test API key</b>."
            )
        await _send_llm_config_panel(query, context, edit=True, extra_footer=footer)
        return

async def cmd_fe_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: Format Engine + RAG stats."""
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        await msg.reply_text("Admin only.")
        return

    def _load_stats() -> dict:
        from sqlalchemy import func

        db = SessionLocal()
        try:
            eff = get_effective_secretary_settings(db)
            ctx_n = db.query(SecretaryUserContext).count()
            know_n = (
                db.query(SecretaryKnowledgeEntry)
                .filter(SecretaryKnowledgeEntry.is_active.is_(True))
                .count()
            )
            phases = {
                str(p or "?"): int(c)
                for p, c in db.query(SecretaryUserContext.current_phase, func.count(SecretaryUserContext.id))
                .group_by(SecretaryUserContext.current_phase)
                .all()
            }
            return {
                "effective": eff,
                "contexts": ctx_n,
                "knowledge": know_n,
                "phases": phases,
                "drafts": count_drafts(db),
            }
        finally:
            db.close()

    try:
        stats = await asyncio.to_thread(_load_stats)
    except Exception as e:
        await msg.reply_text(f"Stats failed: {e}")
        return
    eff = stats["effective"]
    phase_lines = ", ".join(f"{k}:{v}" for k, v in (stats.get("phases") or {}).items()) or "none"
    text = (
        "<b>Format Engine (admin)</b>\n"
        f"FE enabled: <code>{eff.get('format_engine_enabled')}</code>\n"
        f"RAG: <code>{eff.get('rag_enabled')}</code> (top {eff.get('rag_top_k')})\n"
        f"LLM refine on phase change: <code>{eff.get('llm_refine_on_phase_change')}</code>\n"
        f"User contexts: <b>{stats['contexts']}</b>\n"
        f"FAQ chunks: <b>{stats['knowledge']}</b>\n"
        f"Phases: {html.escape(phase_lines)}\n"
        f"Pending business drafts: <b>{stats['drafts']}</b>\n"
        "\nPeople formats: <code>/formats</code> (live cards in this DM).\n"
        "Dashboard: Automation → Bots &amp; workers, or System → Secretary / FAQ."
    )
    await _reply(msg, text, context, parse_mode="HTML")


_FE_WATCH_KEY = "fe_format_watch"
_FE_ROSTER_PAGE = 8
_FE_LIVE_MAX = 6


def _fe_watch(context: ContextTypes.DEFAULT_TYPE) -> dict:
    data = context.application.bot_data.get(_FE_WATCH_KEY)
    if not isinstance(data, dict):
        data = {
            "enabled": False,
            "chat_id": None,
            "roster_message_id": None,
            "roster_page": 0,
            "roster_q": "",
            "cards": {},
            "order": [],
        }
        context.application.bot_data[_FE_WATCH_KEY] = data
    data.setdefault("cards", {})
    data.setdefault("order", [])
    data.setdefault("roster_q", "")
    data.setdefault("roster_page", 0)
    return data


def _fe_roster_keyboard(*, page: int, total: int, live: bool, query: str = "") -> InlineKeyboardMarkup:
    pages = max(1, (max(0, int(total)) + _FE_ROSTER_PAGE - 1) // _FE_ROSTER_PAGE)
    page = max(0, min(int(page), pages - 1))
    prev_p = max(0, page - 1)
    next_p = min(pages - 1, page + 1)
    live_label = "⏸ Pause live" if live else "▶ Live on"
    live_data = "sec:fe:live:0" if live else "sec:fe:live:1"
    nav = [
        InlineKeyboardButton("◀", callback_data=f"sec:fe:p:{prev_p}"),
        InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="sec:fe:r"),
        InlineKeyboardButton("▶", callback_data=f"sec:fe:p:{next_p}"),
    ]
    return InlineKeyboardMarkup(
        [
            nav,
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="sec:fe:r"),
                InlineKeyboardButton(live_label, callback_data=live_data),
            ],
        ]
    )


def _fe_people_keyboard(items: list[dict]) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    for item in items:
        uid = int(item.get("telegram_user_id") or 0)
        if not uid:
            continue
        from app.services.secretary_report_copy import format_who_label

        who = format_who_label(item)
        phase = str(item.get("current_phase") or "introduction")
        mark = {"introduction": "👋", "engagement": "💬", "support": "🛟", "recovery": "🔁"}.get(phase, "•")
        label = f"{mark} {who}"[:32]
        rows.append([InlineKeyboardButton(label, callback_data=f"sec:fe:v:{uid}")])
    return rows


def _fe_card_keyboard(uid: int, *, live: bool) -> InlineKeyboardMarkup:
    pin_label = "📌 Keep live" if live else "📌 Pin live"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data=f"sec:fe:v:{uid}"),
                InlineKeyboardButton(pin_label, callback_data=f"sec:fe:pin:{uid}"),
            ],
            [InlineKeyboardButton("◀ Roster", callback_data="sec:fe:r")],
        ]
    )


def _fe_not_modified(err: Exception) -> bool:
    return "not modified" in str(err).lower()


async def _fe_safe_edit(
    bot,
    *,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> bool:
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
        return True
    except TelegramError as e:
        if _fe_not_modified(e):
            return True
        logger.debug("format card edit failed chat=%s mid=%s: %s", chat_id, message_id, e)
        return False


async def _fe_send_or_edit(
    bot,
    *,
    chat_id: int,
    message_id: int | None,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
):
    if message_id:
        ok = await _fe_safe_edit(
            bot, chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup
        )
        if ok:
            return message_id
    sent = await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )
    return int(sent.message_id)


async def _fe_load_roster(page: int, query: str) -> dict:
    offset = max(0, int(page)) * _FE_ROSTER_PAGE
    return await asyncio.to_thread(
        list_recent_contexts, q=query or None, limit=_FE_ROSTER_PAGE, offset=offset
    )


async def _fe_render_roster(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    chat_id: int,
    page: int | None = None,
    query: str | None = None,
    live: bool | None = None,
) -> None:
    from app.services.secretary_report_copy import format_formats_roster_html

    watch = _fe_watch(context)
    if page is not None:
        watch["roster_page"] = max(0, int(page))
    if query is not None:
        watch["roster_q"] = query.strip().lstrip("@")
    if live is not None:
        watch["enabled"] = bool(live)
    watch["chat_id"] = int(chat_id)
    page_n = int(watch.get("roster_page") or 0)
    q = str(watch.get("roster_q") or "")
    data = await _fe_load_roster(page_n, q)
    total = int(data.get("total") or 0)
    items = list(data.get("items") or [])
    pages = max(1, (total + _FE_ROSTER_PAGE - 1) // _FE_ROSTER_PAGE)
    if page_n >= pages:
        page_n = pages - 1
        watch["roster_page"] = page_n
        data = await _fe_load_roster(page_n, q)
        total = int(data.get("total") or 0)
        items = list(data.get("items") or [])
    html_body = format_formats_roster_html(
        items=items,
        total=total,
        page=page_n,
        page_size=_FE_ROSTER_PAGE,
        live=bool(watch.get("enabled")),
        query=q,
    )
    kb_rows = _fe_people_keyboard(items)
    kb_rows.extend(
        _fe_roster_keyboard(page=page_n, total=total, live=bool(watch.get("enabled")), query=q).inline_keyboard
    )
    kb = InlineKeyboardMarkup(kb_rows)
    mid = await _fe_send_or_edit(
        context.bot,
        chat_id=chat_id,
        message_id=watch.get("roster_message_id"),
        text=html_body,
        reply_markup=kb,
    )
    watch["roster_message_id"] = mid


async def _fe_render_card(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    chat_id: int,
    uid: int,
    pin: bool = False,
    snapshot: bool = False,
) -> None:
    from app.services.secretary_report_copy import format_interaction_format_html

    payload = await asyncio.to_thread(get_context_display, telegram_user_id=int(uid))
    if not payload:
        await context.bot.send_message(
            chat_id=chat_id,
            text="No Format Engine card for that person yet.",
        )
        return
    watch = _fe_watch(context)
    watch["chat_id"] = int(chat_id)
    live = bool(watch.get("enabled")) or pin
    if pin:
        watch["enabled"] = True
    html_body = format_interaction_format_html(payload, live=live and not snapshot, snapshot=snapshot)
    kb = _fe_card_keyboard(int(uid), live=live)
    cards: dict = watch.setdefault("cards", {})
    order: list = watch.setdefault("order", [])
    existing = cards.get(int(uid))
    mid = await _fe_send_or_edit(
        context.bot,
        chat_id=chat_id,
        message_id=int(existing) if existing else None,
        text=html_body,
        reply_markup=kb,
    )
    cards[int(uid)] = mid
    if int(uid) in order:
        order.remove(int(uid))
    order.append(int(uid))
    while len(order) > _FE_LIVE_MAX:
        evict = int(order.pop(0))
        if evict == int(uid):
            continue
        evict_mid = cards.pop(evict, None)
        if evict_mid:
            stale = await asyncio.to_thread(get_context_display, telegram_user_id=evict)
            if stale:
                stale_html = format_interaction_format_html(stale, live=False, snapshot=True)
                await _fe_safe_edit(
                    context.bot,
                    chat_id=chat_id,
                    message_id=int(evict_mid),
                    text=stale_html,
                    reply_markup=_fe_card_keyboard(evict, live=False),
                )


async def _fe_open_live_board(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    chat_id: int,
    query: str = "",
    enable_live: bool = True,
) -> None:
    watch = _fe_watch(context)
    watch["enabled"] = bool(enable_live)
    watch["chat_id"] = int(chat_id)
    watch["roster_page"] = 0
    watch["roster_q"] = (query or "").strip().lstrip("@")
    await _fe_render_roster(context, chat_id=chat_id)
    if not enable_live:
        return
    data = await _fe_load_roster(0, watch.get("roster_q") or "")
    for item in list(data.get("items") or [])[:_FE_LIVE_MAX]:
        uid = int(item.get("telegram_user_id") or 0)
        if uid:
            await _fe_render_card(context, chat_id=chat_id, uid=uid, pin=True)


async def _touch_format_live(context: ContextTypes.DEFAULT_TYPE, uid: int | None) -> None:
    """Edit the operator's live format card (and roster) after a customer turn."""
    if not uid:
        return
    watch = _fe_watch(context)
    chat_id = watch.get("chat_id")
    if not watch.get("enabled") or not chat_id:
        return
    chat_id = int(chat_id)
    await _fe_render_card(context, chat_id=chat_id, uid=int(uid), pin=True)
    await _fe_render_roster(context, chat_id=chat_id)


async def _touch_format_live_safe(context: ContextTypes.DEFAULT_TYPE, uid: int | None) -> None:
    try:
        await asyncio.sleep(0.4)
        await _touch_format_live(context, uid)
    except Exception:
        logger.debug("format live refresh failed uid=%s", uid, exc_info=True)


def _schedule_format_live(context: ContextTypes.DEFAULT_TYPE, uid: int | None) -> None:
    if not uid:
        return
    try:
        context.application.create_task(_touch_format_live_safe(context, int(uid)))
    except Exception:
        logger.debug("format live schedule failed uid=%s", uid, exc_info=True)


async def cmd_formats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: Format Engine people cards, with live in-place updates in this DM."""
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return
    chat_id = int(msg.chat_id)
    args = [str(a).strip() for a in (context.args or []) if str(a).strip()]
    joined = " ".join(args).strip()
    lower = joined.lower()
    if lower in {"off", "stop", "pause"}:
        watch = _fe_watch(context)
        watch["enabled"] = False
        watch["chat_id"] = chat_id
        await _fe_render_roster(context, chat_id=chat_id, live=False)
        await _reply(msg, "Format live updates <b>paused</b>. Send <code>/formats</code> to resume.", context, parse_mode="HTML")
        return
    if lower in {"live", "on"}:
        await _fe_open_live_board(context, chat_id=chat_id, enable_live=True)
        return
    lookup = joined.lstrip("@")
    if lookup and lookup.lower() not in {"live", "on"}:
        payload = None
        if lookup.isdigit():
            payload = await asyncio.to_thread(get_context_display, telegram_user_id=int(lookup))
        if payload is None:
            found = await asyncio.to_thread(list_recent_contexts, q=lookup, limit=1, offset=0)
            items = list(found.get("items") or [])
            if items:
                payload = await asyncio.to_thread(
                    get_context_display, telegram_user_id=int(items[0]["telegram_user_id"])
                )
        if payload is None:
            await _reply(
                msg,
                f"No format for <code>{html.escape(lookup)}</code>. Try <code>/formats</code> for the roster.",
                context,
                parse_mode="HTML",
            )
            return
        watch = _fe_watch(context)
        watch["enabled"] = True
        watch["chat_id"] = chat_id
        await _fe_render_card(context, chat_id=chat_id, uid=int(payload["telegram_user_id"]), pin=True)
        return
    await _fe_open_live_board(context, chat_id=chat_id, enable_live=True)


async def on_format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("sec:fe:"):
        return
    if not _can_manage_drafts(update):
        await query.answer("Admin only.", show_alert=True)
        return
    await query.answer()
    chat = query.message.chat if query.message else update.effective_chat
    if not chat:
        return
    chat_id = int(chat.id)
    parts = query.data.split(":")
    # sec:fe:<action>[:arg]
    action = parts[2] if len(parts) > 2 else ""
    arg = parts[3] if len(parts) > 3 else ""
    watch = _fe_watch(context)
    watch["chat_id"] = chat_id
    if action == "r":
        await _fe_render_roster(context, chat_id=chat_id)
        return
    if action == "p" and arg.isdigit():
        await _fe_render_roster(context, chat_id=chat_id, page=int(arg))
        return
    if action == "live":
        enable = arg != "0"
        watch["enabled"] = enable
        if enable:
            await _fe_open_live_board(context, chat_id=chat_id, query=str(watch.get("roster_q") or ""), enable_live=True)
        else:
            await _fe_render_roster(context, chat_id=chat_id, live=False)
        return
    if action in {"v", "pin"} and arg.lstrip("-").isdigit():
        await _fe_render_card(context, chat_id=chat_id, uid=int(arg), pin=True)
        return
    await query.answer("Unknown formats action.", show_alert=True)


async def _send_inbox_digest(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    title: str,
    limit: int = 20,
    category: str | None = None,
    min_severity: str | None = None,
    unread_only: bool = False,
    empty_hint: str = "Nothing here — you're caught up.",
) -> None:
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return
    events = list_inbox_events(
        limit=limit,
        category=category,
        min_severity=min_severity,  # type: ignore[arg-type]
        unread_only=unread_only,
    )
    text = format_inbox_digest(events, title=title, empty_hint=empty_hint)
    try:
        await _reply(msg, text, context, parse_mode="HTML", disable_web_page_preview=True)
    except TelegramError as exc:
        logger.warning("inbox digest HTML rejected (%s); sending plain fallback", exc)
        plain = re.sub(r"<[^>]+>", "", text)
        plain = (
            f"{title}\n\n{plain.strip()[:3500]}\n\n"
            "(HTML send failed — this is the plain fallback.)"
        )
        await _reply(msg, plain[:4096], context, disable_web_page_preview=True)


async def cmd_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = [a.lower() for a in (context.args or [])]
    if args and args[0] in ("issues", "recurring", "stuck"):
        msg = update.effective_message
        if not msg or not _can_manage_drafts(update):
            if msg:
                await _reply_inbox_denied(msg, context)
            return
        from app.services.admin_inbox import format_recurring_issues_html, list_recurring_issues

        await _reply(
            msg,
            format_recurring_issues_html(list_recurring_issues(min_count=1, limit=15)),
            context,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return
    await _send_inbox_digest(update, context, title="TBCC Inbox", limit=20)


async def cmd_inbox_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_inbox_digest(
        update,
        context,
        title="Unread",
        limit=30,
        unread_only=True,
        empty_hint="No unread items — use /read after you've reviewed the feed.",
    )


async def cmd_inbox_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_inbox_digest(update, context, title="Payment", category="payment", limit=15)


async def cmd_inbox_loot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_inbox_digest(update, context, title="Loot", category="loot", limit=15)


async def cmd_inbox_ops(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_inbox_digest(update, context, title="Ops", category="ops", limit=15)


async def cmd_inbox_critical(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_inbox_digest(
        update,
        context,
        title="Critical & important",
        limit=25,
        min_severity="important",
    )


async def cmd_inbox_read(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return
    mark_inbox_read()
    await _reply(
        msg,
        "✅ Inbox marked as read. /now will stay quiet until new events arrive.",
        context,
    )


async def cmd_inbox_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return
    last_read = get_last_read_ts()
    unread = list_inbox_events(limit=100, unread_only=True)
    total = list_inbox_events(limit=100)
    focus = get_focus_state()
    usage = triage_usage_today()
    from app.services.secretary_report_copy import format_inbox_status_html

    await _reply(
        msg,
        format_inbox_status_html(
            capture_on=inbox_enabled(),
            stored=len(total),
            unread=len(unread),
            last_read_set=last_read > 0,
            focus=str(focus.get("profile") or "off"),
            lock_events=lock_events_recent_count(),
            triage_on=triage_enabled(),
            triage_used=int(usage.get("used") or 0),
            triage_cap=int(usage.get("cap") or 0),
        ),
        context,
        parse_mode="HTML",
    )


def _copy_text_keyboard(text: str, *, prefix: str = "📋 Copy") -> InlineKeyboardMarkup | None:
    """Telegram copy_text buttons (256 chars each). Returns None if client/API unsupported."""
    chunk_size = 256
    cap = chunk_size * 8
    body = (text or "")[:cap]
    if not body:
        return None
    chunks = [body[i : i + chunk_size] for i in range(0, len(body), chunk_size)]
    rows: list[list[InlineKeyboardButton]] = []
    try:
        for i, chunk in enumerate(chunks):
            label = prefix if len(chunks) == 1 else f"{prefix} {i + 1}/{len(chunks)}"
            rows.append([InlineKeyboardButton(label, copy_text=CopyTextButton(text=chunk))])
    except TypeError:
        return None
    return InlineKeyboardMarkup(rows) if rows else None


def _format_hub_digest(hub: str, *, max_lines: int = 12) -> str:
    """Plain-English digest of error-hub tail for Telegram (not raw log dump)."""
    from app.services.error_suggestions import suggest_fix_for_hub_line

    raw_lines = [ln.strip() for ln in (hub or "").splitlines() if ln.strip()][-max_lines:]
    out: list[str] = []
    seen_fix: set[str] = set()
    hub_line = re.compile(
        r"^\[(?P<ts>[^\]]+)\]\s*\[(?P<svc>[^\]]+)\]\s*\[(?P<lvl>[^\]]+)\]\s*(?P<body>.*)$"
    )
    for line in raw_lines:
        m = hub_line.match(line)
        if m:
            svc = m.group("svc")
            body = m.group("body")
            fix = suggest_fix_for_hub_line(body, svc)
            if fix and fix not in seen_fix:
                out.append(f"• {fix}")
                seen_fix.add(fix)
        elif line not in seen_fix:
            out.append(line[:200])
    return "\n".join(out) if out else "(error hub empty)"


def _triage_copy_keyboard(bundle: str) -> InlineKeyboardMarkup | None:
    return _copy_text_keyboard(bundle, prefix="📋 Copy bundle")


async def cmd_relief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return

    def _apply() -> dict:
        return apply_focus_profile(
            "telegram_relief",
            reason="Secretary /relief (manual)",
            auto=False,
        )

    result = await asyncio.to_thread(_apply)
    ok = bool(result.get("ok"))
    stopped = result.get("stopped_services") or []
    text = (
        "⚡ <b>Telegram relief</b> "
        + ("applied." if ok else "failed — check backend logs.")
        + "\n"
        f"Stopped: <code>{html.escape(', '.join(stopped) if stopped else 'none')}</code>"
    )
    await _reply(msg, text, context, parse_mode="HTML")


async def cmd_focus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return
    st = get_focus_state()
    await _reply(
        msg,
        "🎯 <b>Focus profile</b>\n\n"
        f"Profile: <code>{html.escape(str(st.get('profile') or 'off'))}</code>\n"
        f"Reason: {html.escape(str(st.get('reason') or '—'))}\n"
        f"Since: <code>{html.escape(str(st.get('since') or '—'))}</code>\n"
        f"Lock events (recent): <code>{lock_events_recent_count()}</code>\n\n"
        "Use <b>/relief</b> for telegram_relief · API <code>GET /ops/focus</code>",
        context,
        parse_mode="HTML",
    )


async def cmd_triage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return
    args = context.args or []
    event_id = args[0].strip() if args else ""
    if not event_id:
        events = list_inbox_events(limit=1, category="ops", min_severity="important")  # type: ignore[arg-type]
        if not events:
            await _reply(
                msg,
                "No recent ops events. Pass an id: <code>/triage event_id</code>",
                context,
                parse_mode="HTML",
            )
            return
        event_id = str(events[0].get("id") or "")

    ev = get_inbox_event_by_id(event_id)
    bundle = build_triage_bundle(ev, event_id=event_id)
    kb = _triage_copy_keyboard(bundle)
    kwargs: dict = {"parse_mode": "HTML"}
    if kb:
        kwargs["reply_markup"] = kb
    preview = html.escape(bundle[:3500])
    await _reply(
        msg,
        f"🧰 <b>Triage bundle</b> · <code>{html.escape(event_id)}</code>\n\n<pre>{preview}</pre>",
        context,
        **kwargs,
    )


def _internal_api_headers() -> dict[str, str]:
    key = (
        (os.getenv("TBCC_SECRETARY_INTERNAL_API_KEY") or os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()
    )
    return {"X-TBCC-Internal-Key": key} if key else {}


def _resolve_invoice_order_id(event: dict | None) -> int | None:
    if not event:
        return None
    meta = event.get("meta") or {}
    raw = meta.get("order_id")
    if raw is not None:
        try:
            oid = int(raw)
            if oid > 0:
                return oid
        except (TypeError, ValueError):
            pass
    ref = str(meta.get("reference_code") or "").strip()
    if not ref:
        return None
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.get(
                f"{API_BASE}/external-payment-orders/pending",
                headers=_internal_api_headers(),
            )
            if not r.is_success:
                return None
            rows = r.json()
            if not isinstance(rows, list):
                return None
            for row in rows:
                if isinstance(row, dict) and str(row.get("reference_code") or "") == ref:
                    try:
                        return int(row.get("id"))
                    except (TypeError, ValueError):
                        return None
    except Exception as e:
        logger.warning("resolve invoice order_id failed: %s", e)
    return None


def _invoice_order_action_sync(order_id: int, *, approve: bool) -> tuple[bool, str]:
    path = "mark-paid" if approve else "cancel"
    try:
        with httpx.Client(timeout=45.0) as client:
            r = client.post(
                f"{API_BASE}/external-payment-orders/{order_id}/{path}",
                headers=_internal_api_headers(),
                json={},
            )
            if r.is_success:
                data = r.json() if r.content else {}
                if approve and data.get("idempotent"):
                    return True, "Already fulfilled — access was granted earlier."
                if approve:
                    return True, "Sale approved — subscription/access granted."
                return True, "Pending order denied and cleared."
            detail = ""
            try:
                body = r.json()
                if isinstance(body, dict):
                    detail = str(body.get("detail") or body.get("error") or "")
            except Exception:
                detail = (r.text or "")[:200]
            if r.status_code == 403:
                return False, "API rejected key — set TBCC_INTERNAL_API_KEY in tbcc/.env and restart secretary + API."
            return False, detail or f"API HTTP {r.status_code}"
    except httpx.ConnectError:
        return False, f"Could not reach TBCC API at {API_BASE}."
    except Exception as e:
        return False, str(e)


async def on_invoice_inbox_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.data:
        return
    if not _can_manage_drafts(update):
        await q.answer("Admin only.", show_alert=True)
        return
    parts = q.data.split(":")
    if len(parts) < 3 or parts[0] != "inv" or parts[1] not in ("ok", "no"):
        return
    approve = parts[1] == "ok"
    event_id = parts[2]
    await q.answer("Working…")

    ev = get_inbox_event_by_id(event_id)
    order_id = _resolve_invoice_order_id(ev)
    if not order_id:
        await q.answer("Order not found (already handled or missing order_id).", show_alert=True)
        return

    ok, msg = await asyncio.to_thread(_invoice_order_action_sync, order_id, approve=approve)
    await q.edit_message_reply_markup(reply_markup=None)
    if q.message:
        prefix = "✅" if ok and approve else ("✗" if ok else "⚠️")
        await q.message.reply_text(f"{prefix} {html.escape(msg)}", parse_mode="HTML")


async def on_ops_inbox_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.data:
        return
    if not _can_manage_drafts(update):
        await q.answer("Admin only.", show_alert=True)
        return
    parts = q.data.split(":")
    if len(parts) < 3 or parts[0] != "ops":
        return
    action = parts[1]
    await q.answer()

    if action == "fw" and len(parts) >= 4:
        sub, fw_id = parts[2], parts[3]

        def _fw() -> dict:
            if sub == "ok":
                return approve_action(fw_id, operator="secretary")
            return reject_action(fw_id, operator="secretary")

        result = await asyncio.to_thread(_fw)
        if q.message:
            if sub == "ok" and result.get("handoff"):
                handoff = html.escape(str(result.get("handoff") or "")[:3500])
                await q.message.reply_text(
                    f"✅ Approved — paste into Claude Code:\n\n<pre>{handoff}</pre>",
                    parse_mode="HTML",
                )
            elif sub == "ok":
                await q.message.reply_text("✅ Flywheel action approved and executed.", parse_mode="HTML")
            else:
                await q.message.reply_text("✗ Flywheel action rejected.", parse_mode="HTML")
        await q.edit_message_reply_markup(reply_markup=None)
        return

    event_id = parts[2]
    if action == "relief":

        def _apply() -> dict:
            return apply_focus_profile(
                "telegram_relief",
                reason=f"Secretary button (event {event_id})",
                auto=False,
            )

        result = await asyncio.to_thread(_apply)
        ok = bool(result.get("ok"))
        await q.edit_message_reply_markup(reply_markup=None)
        if q.message:
            await q.message.reply_text(
                "⚡ Telegram relief " + ("applied." if ok else "failed."),
                parse_mode="HTML",
            )
        return

    ev = get_inbox_event_by_id(event_id)
    if action == "copy":
        bundle = build_triage_bundle(ev, event_id=event_id)
        kb = _triage_copy_keyboard(bundle)
        if q.message:
            await q.message.reply_text(
                f"📋 Paste into Cursor:\n\n<pre>{html.escape(bundle[:3800])}</pre>",
                parse_mode="HTML",
                reply_markup=kb,
            )
        return

    if action == "cursor":

        def _run() -> dict:
            return run_cursor_triage(event_id, source="telegram")

        result = await asyncio.to_thread(_run)
        agent = result.get("agent") or {}
        if agent.get("ok"):
            body = html.escape(str(agent.get("result") or "")[:3500])
            text = f"🤖 <b>Agent triage</b>\n\n{body}"
        else:
            reason = html.escape(str(result.get("reason") or agent.get("error") or "failed"))
            bundle = html.escape(str(result.get("bundle") or build_triage_bundle(ev, event_id=event_id))[:2000])
            text = f"🤖 Agent triage unavailable: {reason}\n\n<pre>{bundle}</pre>"
        if q.message:
            await q.message.reply_text(text, parse_mode="HTML")
        return


async def cmd_skip_backlog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return

    def _run() -> dict:
        from app.services.ops_alerts import skip_hub_alert_backlog

        return skip_hub_alert_backlog()

    result = await asyncio.to_thread(_run)
    await _reply(
        msg,
        "🔕 <b>Alert backlog skipped</b>\n"
        f"Hub offset: <code>{result.get('hub_offset')}</code>\n"
        "Catch-up desktop toasts for old error-hub lines are cleared.",
        context,
        parse_mode="HTML",
    )


async def cmd_toasts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return

    def _load() -> dict:
        from app.services.ops_alerts import get_alert_toast_settings

        return get_alert_toast_settings()

    settings = await asyncio.to_thread(_load)
    cap = int(settings.get("max_toasts_per_2min") or 0)
    await _reply(
        msg,
        _format_toast_budget_text(settings),
        context,
        parse_mode="HTML",
        reply_markup=_admin_toast_submenu_keyboard(cap),
    )


async def cmd_flywheel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return

    def _load() -> dict:
        st = flywheel_status()
        pending = list_pending()
        return {"status": st, "pending": pending}

    data = await asyncio.to_thread(_load)
    st = data["status"]
    pending = data["pending"]
    from app.services.secretary_report_copy import format_flywheel_card_html

    await _reply(
        msg,
        format_flywheel_card_html(status=st, pending=pending),
        context,
        parse_mode="HTML",
    )


async def cmd_direction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: on-demand analytics direction — Top 5 ranked bets."""
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return

    use_llm = bool(context.args and str(context.args[0]).lower() == "llm")
    days = 30
    if context.args:
        for arg in context.args:
            if arg.isdigit():
                days = max(1, min(366, int(arg)))
                break

    def _run() -> dict:
        from app.database.session import SessionLocal
        from app.services.analytics_direction import build_analytics_direction_report

        db = SessionLocal()
        try:
            return build_analytics_direction_report(db, days=days, use_llm=use_llm)
        finally:
            db.close()

    report = await asyncio.to_thread(_run)
    directions = report.get("directions") or []
    narrative = report.get("narrative")
    from app.services.secretary_report_copy import format_direction_report_html

    body = format_direction_report_html(
        directions,
        narrative=narrative,
        evidence_summary=report.get("evidence_summary") or {},
        days=days,
    )
    await _reply(msg, body, context, parse_mode="HTML")


async def cmd_surge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: force undress surge blast to @aofmainhub + Loot Room."""
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return

    def _run() -> dict:
        from app.database.session import SessionLocal
        from app.services.undress_surge import run_undress_surge_blast, spike_state

        db = SessionLocal()
        try:
            state = spike_state()
            result = run_undress_surge_blast(db, force=True, reason="secretary_surge")
            return {"state": state, "result": result}
        finally:
            db.close()

    data = await asyncio.to_thread(_run)
    st = data.get("state") or {}
    result = data.get("result") or {}
    from app.services.secretary_report_copy import format_surge_card_html

    await _reply(msg, format_surge_card_html(state=st, result=result), context, parse_mode="HTML")


async def cmd_stack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: tray-aligned stack status (same as Zeus Ops → Stack status)."""
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return
    from app.services.tbcc_stack_control import get_stack_status, stack_control_available

    def _load() -> dict:
        if not stack_control_available():
            return {
                "ok": False,
                "available": False,
                "error": "stack status requires Windows tray supervisor (tbcc-stack-cli.ps1)",
            }
        data = get_stack_status()
        data["available"] = True
        return data

    data = await asyncio.to_thread(_load)
    await _reply(
        msg,
        format_stack_status_html(data),
        context,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("◀ Ops menu", callback_data="zeus:ops:home")]]
        ),
    )


async def on_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    normalized = normalize_menu_callback(query.data)
    if not normalized or not normalized.startswith("sec:menu:"):
        return

    parts = normalized.split(":")
    if len(parts) < 3:
        await query.answer()
        return

    kind = parts[2]
    arg = parts[3] if len(parts) > 3 else ""

    admin_only_kinds = {"hubcopy", "cat", "run", "toast", "aff"}
    if kind in admin_only_kinds and not _can_manage_drafts(update):
        await query.answer("Admin only.", show_alert=True)
        return

    await query.answer()

    if kind == "home":
        await cmd_menu(update, context)
        return

    if kind == "hubcopy":
        hub = tail_error_hub(max_lines=20)
        digest = _format_hub_digest(hub)
        kb = _copy_text_keyboard(digest, prefix="📋 Copy digest")
        if query.message:
            from io import BytesIO

            doc = BytesIO(hub.encode("utf-8"))
            doc.name = "tbcc-error-hub-tail.txt"
            try:
                await query.message.reply_document(
                    document=doc,
                    caption="Raw error hub tail (last 20 lines) — open to copy/search.",
                )
            except TelegramError as e:
                logger.warning("hub copy document failed: %s", e)
            hint = (
                "Tap <b>Copy digest</b> below (official Telegram; AyuGram may not support copy buttons — use the .txt file)."
                if kb
                else "Use the attached <b>.txt</b> file to copy (this client does not support inline copy buttons)."
            )
            await query.message.reply_text(
                "📋 <b>Error hub digest</b>\n\n"
                f"<pre>{html.escape(digest[:3500])}</pre>\n\n"
                f"<i>{hint}</i>",
                parse_mode="HTML",
                reply_markup=kb,
            )
        return

    if kind == "aff":
        if arg == "add":
            context.user_data[PENDING_AFFILIATE_LINK] = True
            if query.message:
                await query.message.reply_text(
                    "🔗 <b>Add sponsor link</b>\n\n"
                    "Paste your affiliate URL in the next message.\n"
                    "Optional: <code>Label|https://…</code>\n"
                    "Prefix <code>sfw</code> for @thecheckoutlist only.\n\n"
                    "Example:\n"
                    "<code>https://www.cometapi.com/console/login?aff=ogsT</code>\n\n"
                    "Auto-routes SFW (Rakuten, Cursor, Chime…) → Checkout List; "
                    "NSFW → Buffer X · TG footers · link hub · loot rolls.\n"
                    "Cancel: <code>/cancel</code>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("◀ More menu", callback_data="zeus:more:home")]]
                    ),
                )
        elif arg == "cancel":
            context.user_data.pop(PENDING_AFFILIATE_LINK, None)
            if query.message:
                await query.message.reply_text("Cancelled sponsor link intake.")
        else:
            await query.answer("Unknown affiliate action.", show_alert=True)
        return

    if kind in ("subscribe", "shop", "reset", "mystatus"):
        if kind == "subscribe":
            await cmd_subscribe_hint(update, context)
        elif kind == "shop":
            await cmd_shop_hint(update, context)
        elif kind == "reset":
            await cmd_reset(update, context)
        elif kind == "mystatus":
            await cmd_mystatus(update, context)
        return

    if kind == "cat":
        if arg == "net":
            if query.message:
                await query.message.reply_text(
                    "🌐 <b>Network</b>\n\n"
                    "Deep links into AOF bots. Stars checkout stays on the payment bot token.",
                    parse_mode="HTML",
                    reply_markup=_network_submenu_keyboard(),
                )
        elif arg == "inbox":
            if query.message:
                await query.message.reply_text(
                    "📬 <b>Inbox</b>\n\n"
                    "Payment, loot, and ops alerts land here. "
                    "<b>Mark read</b> clears the unread badge for <code>/now</code>.",
                    parse_mode="HTML",
                    reply_markup=_admin_inbox_submenu_keyboard(),
                )
        elif arg == "ops":
            if query.message:
                await query.message.reply_text(
                    "🔧 <b>Ops</b>\n\n"
                    "<b>Stack status</b> — tray-aligned N/M (same as <code>/stack</code>).\n"
                    "<b>Relief</b> — pauses optional bots to reduce Telethon session contention.\n"
                    "<b>Triage</b> — bundles the latest alert plus error-hub tail for Cursor.\n"
                    "<b>Toast budget</b> — cap non-payment desktop notifications (/toasts).\n"
                    "Restarts: tray / <code>tbcc-stack-cli.ps1</code> — not this bot.",
                    parse_mode="HTML",
                    reply_markup=_admin_ops_submenu_keyboard(),
                )
        elif arg == "more":
            if query.message:
                await query.message.reply_text(
                    "⋯ <b>More</b>\n\n"
                    "FAQ previews, payment link hints, <b>Formats</b> (live people cards), sponsor intake, LLM config, and the full command list.",
                    parse_mode="HTML",
                    reply_markup=_admin_more_submenu_keyboard(),
                )
        elif arg == "toasts":
            from app.services.ops_alerts import get_alert_toast_settings

            settings = await asyncio.to_thread(get_alert_toast_settings)
            cap = int(settings.get("max_toasts_per_2min") or 0)
            if query.message:
                await query.message.reply_text(
                    _format_toast_budget_text(settings),
                    parse_mode="HTML",
                    reply_markup=_admin_toast_submenu_keyboard(cap),
                )
        elif arg == "faq":
            if query.message:
                await query.message.reply_text(
                    "⭐ <b>FAQ shortcuts</b>\n\n"
                    "Consumer-facing hints you can preview before sending to a customer.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton("Subscribe hint", callback_data="sec:menu:subscribe"),
                                InlineKeyboardButton("Shop hint", callback_data="sec:menu:shop"),
                            ],
                            [
                                InlineKeyboardButton("My status", callback_data="sec:menu:mystatus"),
                                InlineKeyboardButton("Reset", callback_data="sec:menu:reset"),
                            ],
                            [InlineKeyboardButton("◀ Main menu", callback_data="zeus:home")],
                        ]
                    ),
                )
        elif arg == "pay":
            await cmd_subscribe_hint(update, context)
        else:
            await query.answer("Unknown submenu.", show_alert=True)
        return

    if kind == "toast":
        from app.services.ops_alerts import (
            adjust_max_client_toasts_per_2min,
            get_alert_toast_settings,
            set_max_client_toasts_per_2min,
        )

        if arg == "up":
            cap = await asyncio.to_thread(adjust_max_client_toasts_per_2min, 1)
        elif arg == "down":
            cap = await asyncio.to_thread(adjust_max_client_toasts_per_2min, -1)
        elif arg == "set" and len(parts) > 4:
            cap = await asyncio.to_thread(set_max_client_toasts_per_2min, int(parts[4]))
        else:
            settings = await asyncio.to_thread(get_alert_toast_settings)
            cap = int(settings.get("max_toasts_per_2min") or 0)
            if query.message:
                await query.message.reply_text(
                    _format_toast_budget_text(settings),
                    parse_mode="HTML",
                    reply_markup=_admin_toast_submenu_keyboard(cap),
                )
            return
        settings = await asyncio.to_thread(get_alert_toast_settings)
        text = _format_toast_budget_text(settings)
        if query.message:
            try:
                await query.message.edit_text(
                    text,
                    parse_mode="HTML",
                    reply_markup=_admin_toast_submenu_keyboard(cap),
                )
            except TelegramError:
                await query.message.reply_text(
                    text,
                    parse_mode="HTML",
                    reply_markup=_admin_toast_submenu_keyboard(cap),
                )
        return

    if kind == "run":
        runners = {
            "inbox": cmd_inbox,
            "now": cmd_inbox_now,
            "payment": cmd_inbox_payment,
            "loot": cmd_inbox_loot,
            "ops": cmd_inbox_ops,
            "critical": cmd_inbox_critical,
            "read": cmd_inbox_read,
            "status": cmd_inbox_status,
            "relief": cmd_relief,
            "focus": cmd_focus,
            "triage": cmd_triage,
            "flywheel": cmd_flywheel,
            "config": cmd_config,
            "commands": cmd_commands,
            "skipbacklog": cmd_skip_backlog,
            "toasts": cmd_toasts,
            "stack": cmd_stack,
            "formats": cmd_formats,
        }
        fn = runners.get(arg)
        if fn:
            await fn(update, context)
        else:
            await query.answer("Unknown action.", show_alert=True)
        return

    await query.answer("Unknown menu.", show_alert=True)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_subscribe_hint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if not _allow_rate_limit(user.id):
        await _reply(
            msg,
            "Rate limit — wait a bit, then try again.",
            context,
            parse_mode="HTML",
        )
        return
    pay = _payment_bot_username()
    if not pay:
        await _reply(msg, "Payment bot username is not configured.", context)
        return
    pay_safe = html.escape(pay)
    await _reply(
        msg,
        "Subscriptions (Stars + access) are handled here:\n"
        f'<a href="https://t.me/{pay_safe}">https://t.me/{pay_safe}</a>\n\n'
        "Open that chat and send <b>/subscribe</b>.",
        context,
        parse_mode="HTML",
    )


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    context.user_data.pop(HISTORY_KEY, None)
    context.user_data.pop(BIZ_LINES_KEY, None)
    await _reply(msg, "Conversation context cleared.", context)


async def cmd_shop_hint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if not _allow_rate_limit(user.id):
        await _reply(
            msg,
            "Rate limit — wait a bit, then try again.",
            context,
            parse_mode="HTML",
        )
        return
    pay = _payment_bot_username()
    if not pay:
        await _reply(msg, "Payment bot username is not configured.", context)
        return
    pay_safe = html.escape(pay)
    await _reply(
        msg,
        "Storefront / promos:\n"
        f'<a href="https://t.me/{pay_safe}">https://t.me/{pay_safe}</a>\n\n'
        "Send <b>/shop</b> in that bot.",
        context,
        parse_mode="HTML",
    )


async def cmd_addsponsor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: start sponsor-link intake (same as menu → More → Add sponsor link)."""
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return
    force_lane, body = parse_affiliate_intake_args(context.args or [])
    if body:
        parsed = parse_affiliate_intake_text(body)
        if not parsed:
            await _reply(
                msg,
                "Usage: <code>/addsponsor [sfw] https://…</code> or "
                "<code>/addsponsor Label|https://…</code>",
                context,
                parse_mode="HTML",
            )
            return
        label, url = parsed
        db = SessionLocal()
        try:
            result = await asyncio.to_thread(
                intake_affiliate_sponsor,
                db,
                label=label,
                url=url,
                sync=True,
                force_lane=force_lane,
            )
        finally:
            db.close()
        await _reply(msg, ("✅ " if result.ok else "❌ ") + result.message, context, parse_mode="HTML")
        return
    context.user_data[PENDING_AFFILIATE_LINK] = True
    await _reply(
        msg,
        "🔗 Paste your affiliate URL in the next message "
        "(optional <code>Label|https://…</code> or prefix <code>sfw</code>). Cancel: <code>/cancel</code>",
        context,
        parse_mode="HTML",
    )


async def cmd_sponsors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin DM: list every affiliate sponsor with URL, clicks, attributed ledger $."""
    msg = update.effective_message
    if not msg or not _can_manage_drafts(update):
        if msg:
            await _reply_inbox_denied(msg, context)
        return
    if msg.chat.type != "private":
        await _reply(msg, "Open a private chat with me and send <code>/sponsors</code>.", context, parse_mode="HTML")
        return

    days = 30
    include_inactive = False
    for arg in context.args or []:
        a = (arg or "").strip().lower()
        if a in ("all", "inactive", "+inactive"):
            include_inactive = True
        elif a.isdigit():
            days = max(1, min(366, int(a)))

    def _load() -> dict:
        from app.services.affiliate_sponsor_report import build_affiliate_sponsor_report

        db = SessionLocal()
        try:
            return build_affiliate_sponsor_report(
                db, include_inactive=include_inactive, revenue_days=days
            )
        finally:
            db.close()

    report = await asyncio.to_thread(_load)
    messages = report.get("messages") or ["No affiliate sponsors found."]
    for i, chunk in enumerate(messages):
        await _reply(msg, chunk, context, parse_mode="HTML")
        if i + 1 < len(messages):
            await asyncio.sleep(0.35)



async def on_business_outbound(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Capture operator-typed Telegram Business messages as silent FE assistant turns (G11)."""
    msg = getattr(update, "business_message", None) or update.message
    if not msg or not getattr(msg, "business_connection_id", None) or not msg.from_user or not msg.text:
        return
    customer_uid = msg.chat_id
    if msg.from_user.id == customer_uid:
        return
    mid = getattr(msg, "message_id", None)
    if mid is not None and int(mid) in _sent_business_msg_ids:
        _sent_business_msg_ids.pop(int(mid), None)
        return
    body = msg.text.strip()
    if not body:
        return
    try:
        await asyncio.to_thread(
            record_external_assistant_turn,
            int(customer_uid),
            body,
            str(msg.business_connection_id),
        )
        try:
            _schedule_format_live(context, int(customer_uid))
        except Exception:
            logger.debug("format live refresh after operator business turn failed", exc_info=True)
    except Exception:
        logger.warning("format_engine record_external_assistant_turn failed uid=%s", customer_uid, exc_info=True)


async def on_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or not msg.text:
        return
    if msg.chat.type != "private":
        return

    bc_id = getattr(msg, "business_connection_id", None)
    if bc_id is not None:
        if _is_owner_message(user.id):
            return
        if msg.message_id and _already_processed_business_msg(str(bc_id), user.id, int(msg.message_id)):
            return
    elif not _can_manage_drafts(update):
        try:
            eff = await asyncio.to_thread(get_effective_secretary_settings)
            if not eff.get("public_faq_enabled", True):
                pay = _payment_bot_username()
                hint = f" Open @{pay} for checkout." if pay else ""
                await _reply(
                    msg,
                    "This bot is admin-only. Customer FAQ is handled via the payment bot." + hint,
                    context,
                )
                return
        except Exception as e:
            logger.warning("public_faq gate failed: %s", e)

    if not _allow_rate_limit(user.id):
        await _reply(
            msg,
            "You're sending messages a bit fast — please wait a minute and try again.",
            context,
        )
        return

    user_text = msg.text.strip()
    if not user_text:
        return

    if _can_manage_drafts(update):
        if context.user_data.get(PENDING_LLM_API_KEY):
            if user_text.startswith("/") and user_text.split()[0] != "/cancel":
                await _reply(
                    msg,
                    "Still waiting for API key, or send <code>/cancel</code>.",
                    context,
                    parse_mode="HTML",
                )
                return
            context.user_data.pop(PENDING_LLM_API_KEY, None)
            try:
                saved = await asyncio.to_thread(persist_llm_api_key, user_text)
                test = await asyncio.to_thread(probe_secretary_llm)
            except ValueError as e:
                await _reply(msg, f"Not saved: {html.escape(str(e))}", context, parse_mode="HTML")
                return
            except Exception as e:
                await _reply(msg, f"Save failed: {html.escape(str(e))}", context, parse_mode="HTML")
                return
            footer = (
                f"✅ API key saved (<code>{html.escape(str(saved.get('api_key_hint')))}</code>).\n"
                + _format_llm_test_result(test)
            )
            await _send_llm_config_panel(msg, context, extra_footer=footer)
            return

        if context.user_data.get(PENDING_LLM_BASE_URL):
            if user_text.startswith("/") and user_text.split()[0] != "/cancel":
                await _reply(
                    msg,
                    "Still waiting for endpoint URL, or send <code>/cancel</code>.",
                    context,
                    parse_mode="HTML",
                )
                return
            context.user_data.pop(PENDING_LLM_BASE_URL, None)
            try:
                saved = await asyncio.to_thread(persist_llm_base_url, user_text)
                test = await asyncio.to_thread(probe_secretary_llm)
            except ValueError as e:
                await _reply(msg, f"Not saved: {html.escape(str(e))}", context, parse_mode="HTML")
                return
            except Exception as e:
                await _reply(msg, f"Save failed: {html.escape(str(e))}", context, parse_mode="HTML")
                return
            endpoint = html.escape(str(saved.get("endpoint_url") or "—"))
            footer = f"✅ Endpoint saved.\nCompletions: <code>{endpoint}</code>\n" + _format_llm_test_result(test)
            await _send_llm_config_panel(msg, context, extra_footer=footer)
            return

        if context.user_data.get(PENDING_LLM_MODEL):
            if user_text.startswith("/") and user_text.split()[0] != "/cancel":
                await _reply(
                    msg,
                    "Still waiting for model id, or send <code>/cancel</code>.",
                    context,
                    parse_mode="HTML",
                )
                return
            context.user_data.pop(PENDING_LLM_MODEL, None)
            try:
                saved = await asyncio.to_thread(persist_llm_model, user_text)
                test = await asyncio.to_thread(probe_secretary_llm)
            except ValueError as e:
                await _reply(msg, f"Not saved: {html.escape(str(e))}", context, parse_mode="HTML")
                return
            except Exception as e:
                await _reply(msg, f"Save failed: {html.escape(str(e))}", context, parse_mode="HTML")
                return
            model = html.escape(str(saved.get("model") or "—"))
            footer = f"✅ Model set to <code>{model}</code>.\n" + _format_llm_test_result(test)
            await _send_llm_config_panel(msg, context, extra_footer=footer)
            return

        if context.user_data.get(PENDING_AFFILIATE_LINK):
            if user_text.startswith("/") and user_text.split()[0] != "/cancel":
                await _reply(
                    msg,
                    "Still waiting for sponsor URL, or send <code>/cancel</code>.",
                    context,
                    parse_mode="HTML",
                )
                return
            context.user_data.pop(PENDING_AFFILIATE_LINK, None)
            force_lane = context.user_data.pop("pending_affiliate_force_lane", "auto")
            parsed = parse_affiliate_intake_text(user_text)
            if not parsed:
                await _reply(
                    msg,
                    "Need a valid <code>https://</code> URL. "
                    "Try again via <b>Menu → More → Add sponsor link</b>.",
                    context,
                    parse_mode="HTML",
                )
                return
            label, url = parsed
            db = SessionLocal()
            try:
                result = await asyncio.to_thread(
                    intake_affiliate_sponsor,
                    db,
                    label=label,
                    url=url,
                    sync=True,
                    force_lane=force_lane,
                )
            finally:
                db.close()
            await _reply(
                msg,
                ("✅ " if result.ok else "❌ ") + result.message,
                context,
                parse_mode="HTML",
            )
            return

    if not secretary_llm_configured():
        if _can_manage_drafts(update):
            await _reply(
                msg,
                "FAQ LLM is not configured yet. Send <code>/config</code> to set API key and endpoint.",
                context,
                parse_mode="HTML",
            )
        else:
            await _reply(
                msg,
                "FAQ assistant is offline (no LLM key on the server).",
                context,
            )
        return

    if _can_manage_drafts(update) and context.user_data.get(PENDING_SYSPROMPT_KEY):
        if user_text.startswith("/"):
            if user_text.split()[0] != "/cancel":
                await _reply(
                    msg,
                    "Still waiting for system prompt text, or send <code>/cancel</code>.",
                    context,
                    parse_mode="HTML",
                )
            return
        context.user_data.pop(PENDING_SYSPROMPT_KEY, None)
        try:
            result = await asyncio.to_thread(persist_system_prompt, user_text)
        except ValueError as e:
            await _reply(msg, f"Not saved: {html.escape(str(e))}", context, parse_mode="HTML")
            return
        except Exception as e:
            await _reply(msg, f"Save failed: {html.escape(str(e))}", context, parse_mode="HTML")
            return
        await _reply(
            msg,
            f"✅ System prompt saved (<code>{result['source']}</code>, {result['chars']} chars).",
            context,
            parse_mode="HTML",
        )
        return

    shortcut = _FAQ_KEYBOARD.get(user_text)
    if shortcut == "subscribe":
        await cmd_subscribe_hint(update, context)
        return
    if shortcut == "shop":
        await cmd_shop_hint(update, context)
        return
    if shortcut == "reset":
        await cmd_reset(update, context)
        return
    if shortcut == "mystatus":
        await cmd_mystatus(update, context)
        return
    if user_text == "💬 Type your question below":
        await _reply(
            msg,
            "Type your question in a message below — I'll answer using FAQ knowledge and your thread context.",
            context,
        )
        return

    is_business = bc_id is not None
    is_admin_chat = _can_manage_drafts(update)
    if is_business:
        customer_mode = await asyncio.to_thread(_customer_reply_mode, user.id, is_business=True)
        suggest_mode = customer_mode == "pilot"
    elif is_admin_chat:
        suggest_mode = False
        customer_mode = "auto"
    else:
        customer_mode = await asyncio.to_thread(_customer_reply_mode, user.id, is_business=False)
        suggest_mode = customer_mode == "pilot"

    if not suggest_mode:
        try:
            await _send_chat_action(msg, context, ChatAction.TYPING)
        except Exception as e:
            logger.debug("send_chat_action: %s", e)

    pay = _payment_bot_username()
    extra = ""
    intent = classify_intent(user_text)
    format_ctx_id: int | None = None
    is_new_lead = False
    fe_phase = "introduction"
    fe_count = 0
    if format_engine_enabled():
        who = (user.username or "").strip() or None
        try:
            fe_suffix, format_ctx_id, is_new_lead = await asyncio.to_thread(
                prepare_user_turn, user.id, user_text, username=who
            )
            if fe_suffix:
                extra = extra + "\n\n" + fe_suffix
        except Exception as e:
            logger.warning("format_engine prepare failed uid=%s: %s", user.id, e)
        try:
            summary = await asyncio.to_thread(get_user_context_public_summary, user.id)
            if summary:
                fe_phase = str(summary.get("phase") or fe_phase)
                fe_count = int(summary.get("message_count") or 0)
        except Exception:
            pass
        try:
            _schedule_format_live(context, user.id)
        except Exception:
            logger.debug("format live refresh after user turn failed", exc_info=True)

    extra = extra + "\n\n" + behavior_suffix(
        intent=intent,
        phase=fe_phase,
        message_count=fe_count,
        payment_bot=pay or "aofsubscriptions_bot",
    )

    coach_hint = intent_label(intent)
    if intent != "noise":
        if pay:
            extra = extra + f"\n\nPayment bot username: @{pay}."
        catalog = await fetch_subscription_catalog_snippet(API_BASE)
        if catalog and intent == "buyer":
            extra = extra + "\n\n" + catalog
        try:
            coach_suffix, coach_from_playbook = await asyncio.to_thread(
                build_sales_coach_suffix,
                user_text,
                current_phase=(fe_phase if format_engine_enabled() else None),
            )
            if coach_suffix:
                extra = extra + "\n\n" + coach_suffix
            if coach_from_playbook:
                coach_hint = coach_from_playbook
        except Exception as e:
            logger.warning("secretary sales coach failed uid=%s: %s", user.id, e)
        try:
            sec_eff = await asyncio.to_thread(get_effective_secretary_settings)
            if sec_eff.get("rag_enabled"):
                rag_suffix = await asyncio.to_thread(build_rag_context_suffix, user_text)
                if rag_suffix:
                    extra = extra + "\n\n" + rag_suffix
            prompt_extra = (sec_eff.get("system_prompt_extra") or "").strip()
            if prompt_extra:
                extra = extra + "\n\n" + prompt_extra
        except Exception as e:
            logger.warning("secretary RAG/settings suffix failed uid=%s: %s", user.id, e)
    else:
        coach_hint = intent_label(intent)

    scripted = corpus_candidates(
        user_text,
        intent=intent,
        phase=fe_phase,
        message_count=fe_count,
        payment_bot=pay or "aofsubscriptions_bot",
    )

    if is_new_lead:
        try:
            from app.services.secretary_report_copy import format_new_lead_html

            who_lead = (user.username or "").strip() or str(user.id)
            surface = "business" if is_business else "direct"
            phase = "introduction"
            try:
                summary = await asyncio.to_thread(get_user_context_public_summary, user.id)
                if summary and summary.get("phase"):
                    phase = str(summary["phase"])
            except Exception:
                pass
            await asyncio.to_thread(
                push_admin_inbox_event,
                category="system",
                severity="important",
                title=f"New lead · {who_lead}",
                body=format_new_lead_html(
                    surface=surface,
                    mode_label=mode_label(customer_mode),
                    phase=phase,
                    user_id=user.id,
                    customer_text=user_text,
                ),
                meta={
                    "code": "secretary_new_lead",
                    "telegram_user_id": user.id,
                    "surface": surface,
                    "reply_mode": customer_mode,
                },
                instant=True,
            )
        except Exception:
            logger.debug("secretary new-lead inbox notify failed", exc_info=True)

    if suggest_mode:
        suggest_suffix = (
            "\n\nDrafting for the owner. Customer has not seen bot replies. "
            "Stay dry. Do not pitch checkout unless they asked to buy."
        )
        extra = extra + suggest_suffix
        prev_lines: list[str] = context.user_data.get(BIZ_LINES_KEY) or []
        db_hist_for_suggest: list[dict[str, str]] = []
        if not prev_lines and format_engine_enabled():
            db_hist_for_suggest = await asyncio.to_thread(load_recent_messages_for_llm, user.id)
            if db_hist_for_suggest and db_hist_for_suggest[-1].get("content") == user_text:
                db_hist_for_suggest = db_hist_for_suggest[:-1]
        thread_lines = suggest_customer_lines(prev_lines, db_hist_for_suggest)
        if thread_lines:
            joined = "\n".join(f"- {line[:900]}" for line in thread_lines[-8:])
            user_block = (
                "Earlier customer messages (same thread, no bot replies shown to them):\n"
                f"{joined}\n\nLatest message:\n{user_text}"
            )
        else:
            user_block = user_text
        messages: list[dict[str, str]] = [
            {"role": "system", "content": default_system_prompt()},
            {"role": "user", "content": user_block},
        ]
    else:
        hist: list[dict[str, str]] = context.user_data.get(HISTORY_KEY) or []
        hist = [
            {"role": m["role"], "content": m["content"]}
            for m in hist
            if m.get("role") in ("user", "assistant", "system")
        ]
        if format_engine_enabled() and len(hist) < 2:
            db_hist = await asyncio.to_thread(load_recent_messages_for_llm, user.id)
            if db_hist:
                hist = db_hist[:-1] if db_hist and db_hist[-1].get("content") == user_text else db_hist
        messages = [{"role": "system", "content": default_system_prompt()}]
        messages.extend(hist[-(_history_max_messages()) :])
        messages.append({"role": "user", "content": user_text})

        extra = append_auto_emotion_instruction(extra)
    if suggest_mode:
        extra = append_triage_instruction(extra)
    if scripted:
        cands = apply_candidate_symmetry(user_text, scripted)
        reply = cands["natural"]
        emotion_block = None
    else:
        try:
            chat_kw: dict = {"extra_system_suffix": extra}
            if not suggest_mode:
                phase_key = str(fe_phase or "").strip().lower()
                chat_kw["max_tokens_override"] = (
                    120 if phase_key in ("introduction", "engagement") else 250
                )
            reply = await complete_secretary_chat(messages, **chat_kw)
        except Exception as e:
            logger.warning("secretary LLM failed: %s", e)
            if suggest_mode:
                try:
                    from app.services.admin_inbox import push_admin_inbox_event
                    from app.services.secretary_report_copy import format_draft_fail_html

                    who = (user.username or "").strip() or str(user.id)
                    await asyncio.to_thread(
                        push_admin_inbox_event,
                        category="system",
                        severity="important",
                        title=f"Secretary draft failed · {who}",
                        body=format_draft_fail_html(who=who, customer_text=user_text),
                        meta={"code": "secretary_draft_fail", "telegram_user_id": user.id},
                        instant=True,
                    )
                except Exception:
                    logger.debug("secretary draft-fail inbox notify failed", exc_info=True)
                return
            await _reply(
                msg,
                "Can't reply right now — try again in a minute.",
                context,
            )
            return
        if suggest_mode:
            emotion_block = parse_triage_emotion(reply)
            cands = apply_candidate_symmetry(user_text, parse_triage_candidates(reply))
            reply = cands["natural"]
        else:
            emotion_block, cleaned = extract_emotion_block(reply)
            cleaned = apply_symmetry(user_text, cleaned, variant="natural")
            cands = {"natural": cleaned, "clear": cleaned, "close": cleaned}
            reply = cleaned
        if emotion_block:
            try:
                await asyncio.to_thread(apply_llm_derived_emotion_for_user, user.id, emotion_block)
            except Exception:
                logger.debug("secretary llm emotion ingest failed uid=%s", user.id, exc_info=True)
    natural = cands["natural"]
    if not suggest_mode:
        natural = enforce_brevity(natural)
        reply = natural
        cands["natural"] = natural

    if suggest_mode:
        lines = context.user_data.get(BIZ_LINES_KEY) or []
        lines.append(user_text)
        context.user_data[BIZ_LINES_KEY] = [str(x).strip() for x in lines if str(x).strip()][-16:]

        admin_ids = _draft_notify_chat_ids()
        if admin_ids:
            draft_id = secrets.token_hex(3).upper()
            who = (user.username or "").strip() or "no_username"
            await asyncio.to_thread(
                _save_draft,
                draft_id=draft_id,
                chat_id=msg.chat_id,
                business_connection_id=str(bc_id) if bc_id else None,
                user_id=user.id,
                who=who,
                customer_preview=user_text[:500],
                reply=natural,
                llm_messages=[dict(m) for m in messages],
                extra_system_suffix=extra,
                coach_hint=coach_hint,
                reply_mode=customer_mode,
                candidates=cands,
            )
            try:
                await _send_draft_to_admin(
                    context,
                    draft_id=draft_id,
                    who=who,
                    user_id=user.id,
                    customer_line=user_text,
                    reply_plain=natural,
                    reply_mode=customer_mode,
                    coach_hint=coach_hint,
                    candidates=cands,
                )
                try:
                    from app.services.admin_inbox import push_admin_inbox_event

                    await asyncio.to_thread(
                        push_admin_inbox_event,
                        category="system",
                        severity="important",
                        title=f"Draft ready · {who}",
                        body=(
                            f"In: {html.escape(user_text[:280])}\n\n"
                            f"<b>N</b> <pre>{html.escape(cands.get('natural', '')[:400])}</pre>\n"
                            f"<b>C</b> <pre>{html.escape(cands.get('clear', '')[:400])}</pre>\n"
                            f"<b>X</b> <pre>{html.escape(cands.get('close', '')[:400])}</pre>\n\n"
                            f"<i>Draft <code>{draft_id}</code> — Send N/C/X or /approve {draft_id} n</i>"
                        ),
                        meta={"code": "secretary_draft", "draft_id": draft_id, "telegram_user_id": user.id},
                        instant=True,
                    )
                except Exception:
                    logger.debug("secretary draft inbox ping failed", exc_info=True)
            except Exception as e:
                logger.exception("secretary: could not DM admin draft %s: %s", draft_id, e)
        else:
            logger.error(
                "TBCC_SECRETARY_SUGGEST_DIRECT is on but no ADMIN_TELEGRAM_ID / "
                "TBCC_SECRETARY_SUGGEST_NOTIFY_CHAT_ID — cannot deliver FAQ draft"
            )
    else:
        await _reply(msg, natural[:4096], context)
        try:
            if format_ctx_id is not None:
                await asyncio.to_thread(finalize_assistant_turn, format_ctx_id, natural[:4096])
            else:
                await asyncio.to_thread(finalize_assistant_turn_for_user, user.id, natural[:4096])
        except Exception as e:
            logger.warning("format_engine finalize failed uid=%s ctx=%s: %s", user.id, format_ctx_id, e)
        try:
            _schedule_format_live(context, user.id)
        except Exception:
            logger.debug("format live refresh after assistant turn failed", exc_info=True)
        hist2: list[dict[str, str]] = context.user_data.get(HISTORY_KEY) or []
        hist2 = [
            {"role": m["role"], "content": m["content"]}
            for m in hist2
            if m.get("role") in ("user", "assistant", "system")
        ]
        next_hist = hist2 + [{"role": "user", "content": user_text}, {"role": "assistant", "content": natural}]
        max_keep = _history_max_messages()
        context.user_data[HISTORY_KEY] = next_hist[-max_keep:]


async def on_unsupported_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Voice/photo/etc. in private — short hint."""
    msg = update.effective_message
    if not msg or msg.chat.type != "private":
        return
    await _reply(
        msg,
        "I can only read <b>text</b> in this version. Type your question, or use /help.",
        context,
        parse_mode="HTML",
    )


async def on_service_message_cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete 'X left the group/channel' only — keep join welcome messages visible."""
    from bots.leave_message_cleanup import delete_leave_service_message

    await delete_leave_service_message(update, bot_label="secretary-bot")


async def _on_app_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Avoid huge tracebacks for transient DNS / TLS blips; python-telegram-bot retries polling."""
    err = context.error
    try:
        from telegram.error import Conflict, Forbidden, NetworkError, RetryAfter

        if isinstance(err, Conflict):
            from bots.error_reporter import log_telegram_conflict_once

            log_telegram_conflict_once("secretary-bot", err)
            return
        if isinstance(err, Forbidden):
            logger.info("Secretary Forbidden (blocked chat): %s", err)
            return
        if isinstance(err, RetryAfter):
            from bots.error_reporter import log_retry_after_once

            log_retry_after_once("secretary-bot", err)
            return
        if isinstance(err, NetworkError):
            logger.warning("Telegram NetworkError (usually transient DNS/connectivity): %s", err)
            return
    except ImportError:
        pass
    logger.error("Secretary bot unhandled error", exc_info=err)
    report_bot_error("secretary-bot", "unhandled", err if err is not None else "unknown")


async def post_init(app: Application) -> None:
    from bots.secretary_storage_deposit import secretary_storage_deposit_enabled

    me = await app.bot.get_me()
    logger.info("Secretary bot online @%s id=%s", me.username, me.id)
    user_commands = [
        BotCommand("start", "Intro, menu & payment bot"),
        BotCommand("help", "Same as /start"),
        BotCommand("subscribe", "Open payment bot for /subscribe"),
        BotCommand("shop", "Open payment bot for /shop"),
        BotCommand("mystatus", "Your FAQ thread phase (Format Engine)"),
        BotCommand("reset", "Clear this chat’s FAQ context"),
    ]
    admin_commands = user_commands + [
        BotCommand("menu", "Main menu (inline buttons)"),
        BotCommand("commands", "Command reference"),
        BotCommand("config", "LLM key + endpoint"),
        BotCommand("inbox", "Admin: recent notifications"),
        BotCommand("now", "Admin: unread inbox"),
        BotCommand("payment", "Admin: payment events"),
        BotCommand("loot", "Admin: loot events"),
        BotCommand("ops", "Admin: ops alerts"),
        BotCommand("critical", "Admin: critical + important"),
        BotCommand("read", "Admin: mark inbox seen"),
        BotCommand("status", "Admin: inbox stats"),
        BotCommand("fe_stats", "Format Engine + RAG stats (admin)"),
        BotCommand("formats", "People formats (live in this DM)"),
        BotCommand("sysprompt", "Admin: view system prompt"),
        BotCommand("set_sysprompt", "Admin: set system prompt"),
        BotCommand("clear_sysprompt", "Admin: clear prompt override"),
        BotCommand("drafts", "List pending business drafts"),
        BotCommand("approve", "Send draft to customer"),
        BotCommand("reject", "Discard draft"),
        BotCommand("redo", "Regenerate draft (pro/casual/short)"),
        BotCommand("as_customer", "Simulate customer DM (admin test)"),
        BotCommand("relief", "Apply telegram_relief focus"),
        BotCommand("stack", "Tray stack status (N/M)"),
        BotCommand("focus", "Focus profile status"),
        BotCommand("triage", "Ops triage bundle for Cursor"),
        BotCommand("flywheel", "Ops flywheel status"),
    ]
    if secretary_storage_deposit_enabled():
        admin_commands.append(BotCommand("deposit", "Storage Hub topic → pool"))
    try:
        await app.bot.set_my_commands(user_commands)
        admin_chat = _admin_notify_chat_id()
        if admin_chat is not None:
            await app.bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_chat))
        if secretary_storage_deposit_enabled():
            try:
                from app.services.storage_topic_deposit import storage_hub_chat_id_int

                await app.bot.set_my_commands(
                    [BotCommand("deposit", "Queue N deduped items into this topic's pool")],
                    scope=BotCommandScopeChat(chat_id=storage_hub_chat_id_int()),
                )
            except Exception as e:
                logger.debug("storage hub deposit commands scope: %s", e)
        await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    except Exception as e:
        logger.warning("set_my_commands / menu: %s", e)
    if inbox_enabled() and _admin_notify_chat_id() is not None:
        push_admin_inbox_event(
            category="system",
            severity="info",
            title="Secretary bot online",
            body="Admin inbox: /inbox or /now in this chat.",
            instant=False,
        )


def _telegram_http_timeout_seconds() -> float:
    raw = os.getenv("TELEGRAM_HTTP_TIMEOUT", "30").strip()
    try:
        return max(5.0, min(120.0, float(raw)))
    except ValueError:
        return 30.0


def _telegram_bootstrap_retries() -> int:
    raw = os.getenv("TELEGRAM_BOOTSTRAP_RETRIES", "5").strip()
    try:
        return int(raw)
    except ValueError:
        return 5


def build_application(token: str | None = None) -> Application | None:
    """Build the secretary Application without starting a poller (Zeus co-host ready)."""
    tok = (token if token is not None else _secretary_token()).strip()
    if not tok:
        return None

    t = _telegram_http_timeout_seconds()
    br = _telegram_bootstrap_retries()
    b = (
        Application.builder()
        .token(tok)
        .post_init(post_init)
        .connect_timeout(t)
        .read_timeout(t)
        .write_timeout(t)
        .pool_timeout(t)
        .get_updates_connect_timeout(t)
        .get_updates_read_timeout(t)
        .get_updates_write_timeout(t)
        .get_updates_pool_timeout(t)
    )
    proxy = os.getenv("TELEGRAM_PROXY", "").strip()
    if proxy:
        b = b.proxy(proxy)
    app = b.build()
    logger.info(
        "Telegram HTTP timeouts: %.1fs (TELEGRAM_HTTP_TIMEOUT); bootstrap_retries=%s%s",
        t,
        br,
        f", proxy={proxy}" if proxy else "",
    )
    admins = sorted(_admin_user_id_set())
    if admins:
        logger.info("Admin inbox access for Telegram user id(s): %s", ", ".join(str(x) for x in admins))
    else:
        logger.warning("No valid ADMIN_TELEGRAM_ID — /inbox and instant payment DMs are disabled")
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("commands", cmd_commands))
    app.add_handler(CommandHandler("config", cmd_config))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe_hint))
    app.add_handler(CommandHandler("shop", cmd_shop_hint))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("mystatus", cmd_mystatus))
    app.add_handler(CommandHandler("fe_stats", cmd_fe_stats))
    app.add_handler(CommandHandler("formats", cmd_formats))
    app.add_handler(CommandHandler("sysprompt", cmd_sysprompt))
    app.add_handler(CommandHandler("set_sysprompt", cmd_set_sysprompt))
    app.add_handler(CommandHandler("clear_sysprompt", cmd_clear_sysprompt))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("addsponsor", cmd_addsponsor))
    app.add_handler(CommandHandler("sponsors", cmd_sponsors))
    app.add_handler(CommandHandler("affiliates", cmd_sponsors))
    app.add_handler(CommandHandler("approve", cmd_approve))
    app.add_handler(CommandHandler("reject", cmd_reject))
    app.add_handler(CommandHandler("drafts", cmd_drafts))
    app.add_handler(CommandHandler("redo", cmd_redo))
    app.add_handler(CommandHandler("as_customer", cmd_as_customer))
    app.add_handler(CommandHandler("inbox", cmd_inbox))
    app.add_handler(CommandHandler("now", cmd_inbox_now))
    app.add_handler(CommandHandler("payment", cmd_inbox_payment))
    app.add_handler(CommandHandler("loot", cmd_inbox_loot))
    app.add_handler(CommandHandler("ops", cmd_inbox_ops))
    app.add_handler(CommandHandler("critical", cmd_inbox_critical))
    app.add_handler(CommandHandler("read", cmd_inbox_read))
    app.add_handler(CommandHandler("status", cmd_inbox_status))
    app.add_handler(CommandHandler("relief", cmd_relief))
    app.add_handler(CommandHandler("stack", cmd_stack))
    app.add_handler(CommandHandler("focus", cmd_focus))
    app.add_handler(CommandHandler("triage", cmd_triage))
    app.add_handler(CommandHandler("flywheel", cmd_flywheel))
    app.add_handler(CommandHandler("direction", cmd_direction))
    app.add_handler(CommandHandler("surge", cmd_surge))
    app.add_handler(CommandHandler("toasts", cmd_toasts))
    app.add_handler(CommandHandler("skipbacklog", cmd_skip_backlog))

    async def _cmd_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from bots.secretary_storage_deposit import cmd_deposit as _storage_deposit

        await _storage_deposit(update, context, is_admin=_can_manage_drafts(update))

    app.add_handler(CommandHandler("deposit", _cmd_deposit))
    app.add_handler(CallbackQueryHandler(on_menu_callback, pattern=r"^(sec:menu:|zeus:)"))
    app.add_handler(CallbackQueryHandler(on_format_callback, pattern=r"^sec:fe:"))
    app.add_handler(CallbackQueryHandler(on_llm_config_callback, pattern=r"^sec:llm:"))
    app.add_handler(CallbackQueryHandler(on_draft_callback, pattern=r"^sec:(ap|rj|rd|mode):"))
    app.add_handler(CallbackQueryHandler(on_ops_inbox_callback, pattern=r"^ops:"))
    app.add_handler(CallbackQueryHandler(on_invoice_inbox_callback, pattern=r"^inv:"))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & (~filters.COMMAND), on_private_text))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~filters.TEXT), on_unsupported_private))
    # PTB 21 has UpdateType.BUSINESS_MESSAGE (no filters.BusinessMessage). group=11 runs after
    # the default group=0 private-text pipeline so customer inbound is handled first.
    app.add_handler(
        MessageHandler(
            filters.UpdateType.BUSINESS_MESSAGE & filters.TEXT & (~filters.COMMAND),
            on_business_outbound,
        ),
        group=11,
    )
    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.LEFT_CHAT_MEMBER,
            on_service_message_cleanup,
        )
    )
    app.add_error_handler(_on_app_error)
    # Stash bootstrap retries for callers that still use run_polling().
    app.bot_data["_telegram_bootstrap_retries"] = br
    try:
        jq = app.job_queue
        if jq is not None:
            jq.run_repeating(_prune_sent_business_job, interval=60.0, first=60.0)
    except Exception:
        logger.debug("secretary sent-business prune job not registered", exc_info=True)
    return app


def main() -> None:
    app = build_application()
    if app is None:
        print("Set TBCC_SECRETARY_BOT_TOKEN (or SECRETARY_BOT_TOKEN) in tbcc/.env — see .env.example")
        return

    br = int(app.bot_data.get("_telegram_bootstrap_retries") or _telegram_bootstrap_retries())
    print(
        "Secretary bot running. FAQ: /start /help /subscribe /shop /reset | "
        "Admin inbox: /inbox /now /payment /loot /ops /critical /read /status /stack /relief /focus /triage /flywheel /toasts /skipbacklog /deposit | "
        "Drafts: /approve /reject /drafts"
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=br)


if __name__ == "__main__":
    main()
