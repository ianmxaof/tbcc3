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

from telegram import BotCommand, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.services.secretary_llm import (
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
    item = _pending_drafts.get(draft_id)
    if not item:
        await msg.reply_text(f"Draft {draft_id} not found (maybe already sent/expired).")
        return
    chat_id = int(item["chat_id"])
    bc_id = str(item["business_connection_id"])
    text = str(item["reply"])
    try:
        await context.bot.send_message(chat_id=chat_id, text=text[:4096], business_connection_id=bc_id)
    except TypeError:
        # Backward compatibility across PTB versions.
        await context.bot.send_message(chat_id=chat_id, text=text[:4096])
    except Exception as e:
        logger.exception("approve failed draft=%s chat=%s bc=%s: %s", draft_id, chat_id, bc_id, e)
        await msg.reply_text(f"Could not send draft {draft_id}: {e}")
        return
    _pending_drafts.pop(draft_id, None)
    await msg.reply_text(f"Sent draft {draft_id}.")


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
        + biz_note
    )
    await msg.reply_text(text, parse_mode="HTML", disable_web_page_preview=True, **_reply_kwargs(msg))


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

    if not _allow_rate_limit(user.id):
        await msg.reply_text(
            "You're sending messages a bit fast — please wait a minute and try again.",
            **_reply_kwargs(msg),
        )
        return

    if not openai_configured():
        await msg.reply_text(
            "FAQ assistant is offline (no OpenAI key on the server). "
            "Set TBCC_OPENAI_API_KEY in tbcc/.env for the backend host.",
            **_reply_kwargs(msg),
        )
        return

    user_text = msg.text.strip()
    if not user_text:
        return

    bc_id = getattr(msg, "business_connection_id", None)
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
            _pending_drafts[draft_id] = {
                "chat_id": msg.chat_id,
                "business_connection_id": str(bc_id),
                "reply": reply[:3500],
                "user_id": user.id,
                "who": (user.username or "").strip() or "no_username",
                "created_at": int(time.time()),
            }
            who = (user.username or "").strip() or "no_username"
            safe_reply = reply[:3500]
            admin_body = (
                "<b>FAQ draft</b> (not sent to customer)\n"
                f"Draft ID: <code>{draft_id}</code>\n"
                f"From: @{html.escape(who)} id <code>{user.id}</code>\n"
                f"Connection: <code>{html.escape(str(bc_id))}</code>\n\n"
                f"<b>Their message</b>\n{html.escape(user_text[:2000])}\n\n"
                f"<b>Suggested reply</b>\n{html.escape(safe_reply)}\n\n"
                f"<b>Commands</b>\n"
                f"<code>/approve {draft_id}</code> to send this reply\n"
                f"<code>/reject {draft_id}</code> to discard\n\n"
                "<i>Server: TBCC_SECRETARY_AUTO_REPLY unset/0 → suggest. Set to 1 for in-thread replies.</i>"
            )
            try:
                await context.bot.send_message(chat_id=admin_id, text=admin_body, parse_mode="HTML")
            except Exception as e:
                logger.exception("secretary: could not DM admin %s: %s", admin_id, e)
        else:
            logger.error(
                "TBCC_SECRETARY_AUTO_REPLY is off but no ADMIN_TELEGRAM_ID / "
                "TBCC_SECRETARY_SUGGEST_NOTIFY_CHAT_ID — cannot deliver FAQ draft"
            )
    else:
        await msg.reply_text(reply[:4096], **_reply_kwargs(msg))
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


async def post_init(app: Application) -> None:
    me = await app.bot.get_me()
    logger.info("Secretary bot online @%s id=%s", me.username, me.id)
    commands = [
        BotCommand("start", "Intro and payment bot link"),
        BotCommand("help", "Same as /start"),
        BotCommand("subscribe", "Open payment bot for /subscribe"),
        BotCommand("shop", "Open payment bot for /shop"),
        BotCommand("reset", "Clear this chat’s FAQ context"),
        BotCommand("approve", "Send a pending draft to customer"),
        BotCommand("reject", "Discard a pending draft"),
        BotCommand("drafts", "List pending draft IDs"),
    ]
    try:
        await app.bot.set_my_commands(commands)
    except Exception as e:
        logger.warning("set_my_commands: %s", e)


def main() -> None:
    token = _secretary_token()
    if not token:
        print("Set TBCC_SECRETARY_BOT_TOKEN (or SECRETARY_BOT_TOKEN) in tbcc/.env — see .env.example")
        return

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe_hint))
    app.add_handler(CommandHandler("shop", cmd_shop_hint))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("approve", cmd_approve))
    app.add_handler(CommandHandler("reject", cmd_reject))
    app.add_handler(CommandHandler("drafts", cmd_drafts))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & (~filters.COMMAND), on_private_text))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~filters.TEXT), on_unsupported_private))

    print("Secretary bot running. Commands: /start /help /subscribe /shop /reset /approve /reject /drafts")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
