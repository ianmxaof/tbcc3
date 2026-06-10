"""
FAQ / consumer secretary bot (Telegram Business Chatbots + direct DMs).

- Answers questions via OpenAI (same keys as dashboard: TBCC_OPENAI_API_KEY).
- Points packs and checkout to the payment bot (TBCC_PAYMENT_BOT_USERNAME / BOT_USERNAME).
- Optional: Telegram Business — replies pass through business_connection_id when present.
- Business chats default to **suggest** (draft DM’d to you); set TBCC_SECRETARY_AUTO_REPLY=1 for in-thread auto-reply.

Run: cd tbcc/backend && python -m bots.secretary_bot

Env: TBCC_SECRETARY_BOT_TOKEN (or SECRETARY_BOT_TOKEN), TBCC_API_URL, TBCC_OPENAI_API_KEY, ADMIN_TELEGRAM_ID (for drafts)
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
import secrets
import sys
import time
from collections import deque
from pathlib import Path

_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from dotenv import load_dotenv

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
from telegram.error import NetworkError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bots.error_reporter import report_bot_error

from app.services.format_engine import (
    finalize_assistant_turn,
    finalize_assistant_turn_for_user,
    format_engine_enabled,
    get_user_context_public_summary,
    load_recent_messages_for_llm,
    prepare_user_turn,
)
from app.services.secretary_rag import build_rag_context_suffix
from app.database.session import SessionLocal
from app.models.secretary_knowledge import SecretaryKnowledgeEntry
from app.models.secretary_user_context import SecretaryUserContext
from app.services.secretary_settings_effective import get_effective_secretary_settings
from app.services.secretary_llm import (
    REDO_STYLE_HINTS,
    complete_secretary_chat,
    default_system_prompt,
    fetch_subscription_catalog_snippet,
    openai_configured,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

API_BASE = (os.getenv("TBCC_SECRETARY_API_URL") or os.getenv("TBCC_API_URL") or "http://127.0.0.1:8000").rstrip("/")

# (user_id, deque of monotonic timestamps)
_rate_log: dict[int, deque[float]] = {}
_pending_drafts: dict[str, dict[str, object]] = {}
_business_msg_seen: dict[str, float] = {}


def _secretary_token() -> str:
    return (os.getenv("TBCC_SECRETARY_BOT_TOKEN") or os.getenv("SECRETARY_BOT_TOKEN") or "").strip()


_DEFAULT_PAYMENT_BOT_USERNAME = "aofsubscriptions_bot"


def _payment_bot_username() -> str:
    """Checkout links must never resolve to this secretary bot (common misconfig: BOT_USERNAME = secretary)."""
    sec = (os.getenv("TBCC_SECRETARY_BOT_USERNAME") or "").strip().lstrip("@")
    u = (
        os.getenv("TBCC_PAYMENT_BOT_USERNAME")
        or os.getenv("BOT_USERNAME")
        or _DEFAULT_PAYMENT_BOT_USERNAME
    ).strip().lstrip("@")
    if sec and u.lower() == sec.lower():
        return _DEFAULT_PAYMENT_BOT_USERNAME
    return u


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


def _allow_rate_limit(user_id: int) -> bool:
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


def _reply_kwargs(message) -> dict:
    bc = getattr(message, "business_connection_id", None)
    if bc is not None:
        return {"business_connection_id": bc}
    return {}


HISTORY_KEY = "secretary_history"
BIZ_LINES_KEY = "secretary_biz_customer_lines"

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


def _payment_inline_keyboard() -> InlineKeyboardMarkup | None:
    pay = _payment_bot_username()
    if not pay:
        return None
    pay_safe = html.escape(pay)
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⭐ Subscribe", url=f"https://t.me/{pay_safe}?start=subscribe"),
                InlineKeyboardButton("🛒 Shop", url=f"https://t.me/{pay_safe}?start=shop"),
            ],
            [
                InlineKeyboardButton("📋 Payment bot chat", url=f"https://t.me/{pay_safe}"),
            ],
        ]
    )


async def _reply_with_keyboards(msg, text: str, *, parse_mode: str = "HTML") -> None:
    kwargs = {**_reply_kwargs(msg), "parse_mode": parse_mode, "disable_web_page_preview": True}
    markup_inline = _payment_inline_keyboard()
    if markup_inline:
        kwargs["reply_markup"] = markup_inline
    await msg.reply_text(text, **kwargs)
    # Reply keyboard is sent as a separate lightweight message so inline + reply can coexist
    try:
        await msg.reply_text(
            "Quick actions:",
            reply_markup=_faq_reply_keyboard(),
            **_reply_kwargs(msg),
        )
    except Exception as e:
        logger.debug("faq reply keyboard: %s", e)


def _auto_reply_in_business() -> bool:
    """When True, Business-connected customer chats get bot replies in-thread. Default False = suggest-only."""
    return os.getenv("TBCC_SECRETARY_AUTO_REPLY", "").strip().lower() in ("1", "true", "yes", "on")


def _admin_notify_chat_id() -> int | None:
    """Where to send draft replies in suggest mode (defaults to ADMIN_TELEGRAM_ID)."""
    raw = (os.getenv("TBCC_SECRETARY_SUGGEST_NOTIFY_CHAT_ID") or os.getenv("ADMIN_TELEGRAM_ID") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _admin_user_id() -> int | None:
    raw = (os.getenv("ADMIN_TELEGRAM_ID") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _can_manage_drafts(update: Update) -> bool:
    """Allow draft actions from configured admin user or notify chat."""
    user = update.effective_user
    chat = update.effective_chat
    admin_uid = _admin_user_id()
    notify_chat = _admin_notify_chat_id()
    if user and admin_uid is not None and user.id == admin_uid:
        return True
    if chat and notify_chat is not None and chat.id == notify_chat:
        return True
    return False


def _is_owner_message(user_id: int) -> bool:
    admin_uid = _admin_user_id()
    return admin_uid is not None and user_id == admin_uid


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


def _draft_keyboard(draft_id: str, reply_plain: str) -> InlineKeyboardMarkup:
    copy_text = reply_plain[:256] if len(reply_plain) > 256 else reply_plain
    row0: list[InlineKeyboardButton] = [
        InlineKeyboardButton("✓ Send", callback_data=f"sec:ap:{draft_id}"),
        InlineKeyboardButton("✗ Drop", callback_data=f"sec:rj:{draft_id}"),
    ]
    try:
        row0.insert(
            0,
            InlineKeyboardButton("📋 Copy", copy_text=CopyTextButton(text=copy_text)),
        )
    except TypeError:
        pass
    row1 = [
        InlineKeyboardButton("↻ Pro", callback_data=f"sec:rd:{draft_id}:pro"),
        InlineKeyboardButton("↻ Casual", callback_data=f"sec:rd:{draft_id}:casual"),
        InlineKeyboardButton("↻ Short", callback_data=f"sec:rd:{draft_id}:short"),
    ]
    return InlineKeyboardMarkup([row0, row1])


def _format_draft_card(
    draft_id: str,
    *,
    who: str,
    user_id: int,
    customer_line: str,
    reply_plain: str,
) -> str:
    who_disp = f"@{html.escape(who)}" if who and who != "no_username" else "no @"
    cust = html.escape(customer_line[:500])
    reply = html.escape(reply_plain[:2800])
    return (
        f"<b>━━ {draft_id} ━━</b>\n"
        f"👤 {who_disp} · <code>{user_id}</code>\n"
        f"📩 {cust}\n\n"
        f"💬 <b>Suggested</b> (Copy button or edit, then /approve)\n"
        f"<pre>{reply}</pre>\n"
        f"<code>/approve {draft_id}</code> · <code>/reject {draft_id}</code> · "
        f"<code>/redo {draft_id} pro|casual|short</code>"
    )


async def _send_draft_to_admin(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    draft_id: str,
    who: str,
    user_id: int,
    customer_line: str,
    reply_plain: str,
) -> None:
    admin_id = _admin_notify_chat_id()
    if admin_id is None:
        return
    body = _format_draft_card(
        draft_id,
        who=who,
        user_id=user_id,
        customer_line=customer_line,
        reply_plain=reply_plain,
    )
    await context.bot.send_message(
        chat_id=admin_id,
        text=body,
        parse_mode="HTML",
        reply_markup=_draft_keyboard(draft_id, reply_plain),
    )


async def _deliver_draft_to_customer(context: ContextTypes.DEFAULT_TYPE, draft_id: str) -> tuple[bool, str]:
    item = _pending_drafts.get(draft_id)
    if not item:
        return False, f"Draft {draft_id} not found."
    chat_id = int(item["chat_id"])
    bc_id = str(item["business_connection_id"])
    text = str(item["reply"])
    try:
        await context.bot.send_message(chat_id=chat_id, text=text[:4096], business_connection_id=bc_id)
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
    _pending_drafts.pop(draft_id, None)
    return True, f"Sent {draft_id}."


async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    if not _can_manage_drafts(update):
        await msg.reply_text("Only the configured admin can approve drafts here.")
        return
    if not context.args:
        await msg.reply_text("Usage: /approve <draft_id>")
        return
    draft_id = str(context.args[0]).strip().upper()
    ok, detail = await _deliver_draft_to_customer(context, draft_id)
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
    if draft_id in _pending_drafts:
        _pending_drafts.pop(draft_id, None)
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
    if not openai_configured():
        await msg.reply_text("OpenAI not configured.")
        return
    draft_id = str(context.args[0]).strip().upper()
    item = _pending_drafts.get(draft_id)
    if not item:
        await msg.reply_text(f"Draft {draft_id} not found.")
        return
    style = (context.args[1].strip().lower() if len(context.args) > 1 else "pro")
    custom = " ".join(context.args[2:]).strip() if len(context.args) > 2 else ""
    llm_messages = item.get("llm_messages")
    if not isinstance(llm_messages, list):
        await msg.reply_text("No LLM context stored for this draft — reject and wait for a new customer message.")
        return
    suffix = REDO_STYLE_HINTS.get(style, "")
    if style == "custom" and custom:
        suffix = f"Rewrite the assistant reply with this instruction: {custom}"
    elif not suffix:
        suffix = REDO_STYLE_HINTS["pro"]
    try:
        reply = await complete_secretary_chat(llm_messages, extra_system_suffix=suffix)
    except Exception as e:
        await msg.reply_text(f"Redo failed: {e}")
        return
    item["reply"] = reply[:3500]
    who = str(item.get("who") or "no_username")
    uid = int(item.get("user_id") or 0)
    cust = str(item.get("customer_preview") or "")
    await _send_draft_to_admin(
        context,
        draft_id=draft_id,
        who=who,
        user_id=uid,
        customer_line=cust,
        reply_plain=reply[:3500],
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
    draft_id = parts[2].upper()
    await query.answer()
    if action == "ap":
        ok, detail = await _deliver_draft_to_customer(context, draft_id)
        if query.message:
            await query.message.reply_text(detail)
        return
    if action == "rj":
        if draft_id in _pending_drafts:
            _pending_drafts.pop(draft_id, None)
            if query.message:
                await query.message.reply_text(f"Dropped {draft_id}.")
        return
    if action == "rd" and len(parts) >= 4:
        style = parts[3].lower()
        item = _pending_drafts.get(draft_id)
        if not item or not isinstance(item.get("llm_messages"), list):
            await query.answer("Draft expired.", show_alert=True)
            return
        suffix = REDO_STYLE_HINTS.get(style, REDO_STYLE_HINTS["pro"])
        try:
            reply = await complete_secretary_chat(item["llm_messages"], extra_system_suffix=suffix)
        except Exception as e:
            await query.answer(f"Redo failed: {e}", show_alert=True)
            return
        item["reply"] = reply[:3500]
        who = str(item.get("who") or "no_username")
        uid = int(item.get("user_id") or 0)
        cust = str(item.get("customer_preview") or "")
        await _send_draft_to_admin(
            context,
            draft_id=draft_id,
            who=who,
            user_id=uid,
            customer_line=cust,
            reply_plain=reply[:3500],
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
    if not _pending_drafts:
        await msg.reply_text("No pending drafts.")
        return
    lines = ["<b>Pending drafts</b>"]
    for did, item in list(_pending_drafts.items())[-20:]:
        who = html.escape(str(item.get("who") or "unknown"))
        uid = html.escape(str(item.get("user_id") or ""))
        lines.append(f"• <code>{did}</code> — @{who} id <code>{uid}</code>")
    lines.append("\nUse <code>/approve DRAFT_ID</code> or <code>/reject DRAFT_ID</code>.")
    await msg.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if not _allow_rate_limit(user.id):
        await msg.reply_text(
            "You are sending requests a bit fast. This assistant is <b>rate-limited</b> per minute — "
            "please wait up to a minute, then try <b>/start</b> or your question again.",
            parse_mode="HTML",
            **_reply_kwargs(msg),
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
    await _reply_with_keyboards(msg, text)


async def cmd_mystatus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if not format_engine_enabled():
        await msg.reply_text(
            "Personalized context tracking is off on the server. You can still ask FAQ questions anytime.",
            **_reply_kwargs(msg),
        )
        return
    summary = await asyncio.to_thread(get_user_context_public_summary, user.id)
    if not summary:
        await msg.reply_text(
            "No saved context yet for this chat — send a question and I'll remember the thread for better answers.",
            **_reply_kwargs(msg),
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
    await msg.reply_text("\n".join(lines), parse_mode="HTML", **_reply_kwargs(msg))


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
                "drafts": len(_pending_drafts),
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
        "\nDashboard: Automation → Bots &amp; workers, or System → Secretary / FAQ."
    )
    await msg.reply_text(text, parse_mode="HTML", **_reply_kwargs(msg))


async def on_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("sec:menu:"):
        return
    await query.answer()
    action = query.data.split(":")[-1]
    if action == "subscribe":
        await cmd_subscribe_hint(update, context)
    elif action == "shop":
        await cmd_shop_hint(update, context)
    elif action == "reset":
        await cmd_reset(update, context)
    elif action == "mystatus":
        await cmd_mystatus(update, context)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_subscribe_hint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if not _allow_rate_limit(user.id):
        await msg.reply_text(
            "Rate limit — wait a bit, then try again.",
            parse_mode="HTML",
            **_reply_kwargs(msg),
        )
        return
    pay = _payment_bot_username()
    if not pay:
        await msg.reply_text("Payment bot username is not configured.", **_reply_kwargs(msg))
        return
    pay_safe = html.escape(pay)
    await msg.reply_text(
        "Subscriptions (Stars + access) are handled here:\n"
        f'<a href="https://t.me/{pay_safe}">https://t.me/{pay_safe}</a>\n\n'
        "Open that chat and send <b>/subscribe</b>.",
        parse_mode="HTML",
        **_reply_kwargs(msg),
    )


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    context.user_data.pop(HISTORY_KEY, None)
    context.user_data.pop(BIZ_LINES_KEY, None)
    await msg.reply_text("Conversation context cleared.", **_reply_kwargs(msg))


async def cmd_shop_hint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if not _allow_rate_limit(user.id):
        await msg.reply_text(
            "Rate limit — wait a bit, then try again.",
            parse_mode="HTML",
            **_reply_kwargs(msg),
        )
        return
    pay = _payment_bot_username()
    if not pay:
        await msg.reply_text("Payment bot username is not configured.", **_reply_kwargs(msg))
        return
    pay_safe = html.escape(pay)
    await msg.reply_text(
        "Storefront / promos:\n"
        f'<a href="https://t.me/{pay_safe}">https://t.me/{pay_safe}</a>\n\n'
        "Send <b>/shop</b> in that bot.",
        parse_mode="HTML",
        **_reply_kwargs(msg),
    )


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

    if not _allow_rate_limit(user.id):
        await msg.reply_text(
            "You're sending messages a bit fast — please wait a minute and try again.",
            **_reply_kwargs(msg),
        )
        return

    if not openai_configured():
        await msg.reply_text(
            "FAQ assistant is offline (no OpenAI key on the server). "
            "Set TBCC_OPENROUTER_API_KEY (TBCC_LLM_PROVIDER=openrouter) or TBCC_OPENAI_API_KEY in tbcc/.env.",
            **_reply_kwargs(msg),
        )
        return

    user_text = msg.text.strip()
    if not user_text:
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
        await msg.reply_text(
            "Type your question in a message below — I'll answer using FAQ knowledge and your thread context.",
            **_reply_kwargs(msg),
        )
        return

    is_business = bc_id is not None
    auto_reply_business = _auto_reply_in_business()
    suggest_only_business = is_business and not auto_reply_business

    if not suggest_only_business:
        try:
            await context.bot.send_chat_action(
                chat_id=msg.chat_id, action=ChatAction.TYPING, **_reply_kwargs(msg)
            )
        except TypeError:
            await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
        except Exception as e:
            logger.debug("send_chat_action: %s", e)

    pay = _payment_bot_username()
    extra = ""
    if pay:
        extra = f"\n\nPayment bot for checkout (tell the user to open @{pay} for /subscribe, /packs, /shop)."

    catalog = await fetch_subscription_catalog_snippet(API_BASE)
    if catalog:
        extra = extra + "\n\n" + catalog

    format_ctx_id: int | None = None
    if format_engine_enabled():
        who = (user.username or "").strip() or None
        try:
            fe_suffix, format_ctx_id = await asyncio.to_thread(
                prepare_user_turn, user.id, user_text, username=who
            )
            if fe_suffix:
                extra = extra + "\n\n" + fe_suffix
        except Exception as e:
            logger.warning("format_engine prepare failed uid=%s: %s", user.id, e)

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

    if suggest_only_business:
        suggest_suffix = (
            "\n\nYou are drafting a **suggested** reply for the business owner. "
            "The customer has **not** seen any prior bot messages in this thread. "
            "Be helpful and concise; the owner may copy, edit, or ignore your text."
        )
        extra = extra + suggest_suffix
        prev_lines: list[str] = context.user_data.get(BIZ_LINES_KEY) or []
        prev_lines = [str(x).strip() for x in prev_lines if str(x).strip()]
        if prev_lines:
            joined = "\n".join(f"- {line[:900]}" for line in prev_lines[-8:])
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

    try:
        reply = await complete_secretary_chat(messages, extra_system_suffix=extra)
    except Exception as e:
        logger.warning("secretary LLM failed: %s", e)
        await msg.reply_text(
            "I couldn't generate a reply right now. Try again in a moment, or open the payment bot for checkout.",
            **_reply_kwargs(msg),
        )
        return

    if suggest_only_business:
        lines = context.user_data.get(BIZ_LINES_KEY) or []
        lines.append(user_text)
        context.user_data[BIZ_LINES_KEY] = [str(x).strip() for x in lines if str(x).strip()][-16:]

        admin_id = _admin_notify_chat_id()
        if admin_id is not None:
            draft_id = secrets.token_hex(3).upper()
            who = (user.username or "").strip() or "no_username"
            safe_reply = reply[:3500]
            _pending_drafts[draft_id] = {
                "chat_id": msg.chat_id,
                "business_connection_id": str(bc_id),
                "reply": safe_reply,
                "user_id": user.id,
                "who": who,
                "customer_preview": user_text[:500],
                "llm_messages": [dict(m) for m in messages],
                "created_at": int(time.time()),
            }
            try:
                await _send_draft_to_admin(
                    context,
                    draft_id=draft_id,
                    who=who,
                    user_id=user.id,
                    customer_line=user_text,
                    reply_plain=safe_reply,
                )
            except Exception as e:
                logger.exception("secretary: could not DM admin %s: %s", admin_id, e)
        else:
            logger.error(
                "TBCC_SECRETARY_AUTO_REPLY is off but no ADMIN_TELEGRAM_ID / "
                "TBCC_SECRETARY_SUGGEST_NOTIFY_CHAT_ID — cannot deliver FAQ draft"
            )
    else:
        await msg.reply_text(reply[:4096], **_reply_kwargs(msg))
        if format_ctx_id is not None:
            try:
                await asyncio.to_thread(finalize_assistant_turn, format_ctx_id, reply[:4096])
            except Exception as e:
                logger.warning("format_engine finalize failed ctx=%s: %s", format_ctx_id, e)
        hist2: list[dict[str, str]] = context.user_data.get(HISTORY_KEY) or []
        hist2 = [
            {"role": m["role"], "content": m["content"]}
            for m in hist2
            if m.get("role") in ("user", "assistant", "system")
        ]
        next_hist = hist2 + [{"role": "user", "content": user_text}, {"role": "assistant", "content": reply}]
        max_keep = _history_max_messages()
        context.user_data[HISTORY_KEY] = next_hist[-max_keep:]


async def on_unsupported_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Voice/photo/etc. in private — short hint."""
    msg = update.effective_message
    if not msg or msg.chat.type != "private":
        return
    await msg.reply_text(
        "I can only read <b>text</b> in this version. Type your question, or use /help.",
        parse_mode="HTML",
        **_reply_kwargs(msg),
    )


def _service_cleanup_enabled() -> bool:
    """Delete join/leave service messages in groups (default on; set =0 to disable)."""
    raw = (os.getenv("TBCC_SECRETARY_CLEAN_SERVICE_MESSAGES") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


async def on_service_message_cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove 'X joined the group' / 'X left the group' service messages."""
    if not _service_cleanup_enabled():
        return
    msg = update.effective_message
    if not msg or not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        return
    if not (msg.new_chat_members or msg.left_chat_member):
        return
    try:
        await msg.delete()
    except Exception as e:
        # Needs "Delete messages" admin right in the group; report once per error text via hub dedup.
        logger.debug("join/leave cleanup failed chat=%s: %s", msg.chat_id, e)
        report_bot_error("secretary-bot", "service-message cleanup", e)


async def _on_app_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Avoid huge tracebacks for transient DNS / TLS blips; python-telegram-bot retries polling."""
    err = context.error
    if isinstance(err, NetworkError):
        logger.warning("Telegram NetworkError (usually transient DNS/connectivity): %s", err)
        return
    logger.error("Secretary bot unhandled error", exc_info=err)
    report_bot_error("secretary-bot", "unhandled", err if err is not None else "unknown")


async def post_init(app: Application) -> None:
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
        BotCommand("fe_stats", "Format Engine + RAG stats (admin)"),
        BotCommand("drafts", "List pending business drafts"),
        BotCommand("approve", "Send draft to customer"),
        BotCommand("reject", "Discard draft"),
        BotCommand("redo", "Regenerate draft (pro/casual/short)"),
    ]
    try:
        await app.bot.set_my_commands(user_commands)
        admin_chat = _admin_notify_chat_id()
        if admin_chat is not None:
            await app.bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_chat))
        await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    except Exception as e:
        logger.warning("set_my_commands / menu: %s", e)


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


def main() -> None:
    token = _secretary_token()
    if not token:
        print("Set TBCC_SECRETARY_BOT_TOKEN (or SECRETARY_BOT_TOKEN) in tbcc/.env — see .env.example")
        return

    t = _telegram_http_timeout_seconds()
    br = _telegram_bootstrap_retries()
    b = (
        Application.builder()
        .token(token)
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
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe_hint))
    app.add_handler(CommandHandler("shop", cmd_shop_hint))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("mystatus", cmd_mystatus))
    app.add_handler(CommandHandler("fe_stats", cmd_fe_stats))
    app.add_handler(CommandHandler("approve", cmd_approve))
    app.add_handler(CommandHandler("reject", cmd_reject))
    app.add_handler(CommandHandler("drafts", cmd_drafts))
    app.add_handler(CommandHandler("redo", cmd_redo))
    app.add_handler(CallbackQueryHandler(on_menu_callback, pattern=r"^sec:menu:"))
    app.add_handler(CallbackQueryHandler(on_draft_callback, pattern=r"^sec:(ap|rj|rd):"))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & (~filters.COMMAND), on_private_text))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~filters.TEXT), on_unsupported_private))
    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER,
            on_service_message_cleanup,
        )
    )
    app.add_error_handler(_on_app_error)

    print("Secretary bot running. Commands: /start /help /subscribe /shop /reset /approve /reject /drafts")
    app.run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=br)


if __name__ == "__main__":
    main()
