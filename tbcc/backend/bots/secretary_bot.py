"""
FAQ / consumer secretary bot (Telegram Business Chatbots + direct DMs).

- Answers questions via OpenAI (same keys as dashboard: TBCC_OPENAI_API_KEY).
- Points packs and checkout to the payment bot (TBCC_PAYMENT_BOT_USERNAME / BOT_USERNAME).
- Optional: Telegram Business — replies pass through business_connection_id when present.

Run: cd tbcc/backend && python -m bots.secretary_bot

Env: TBCC_SECRETARY_BOT_TOKEN (or SECRETARY_BOT_TOKEN), TBCC_API_URL, TBCC_OPENAI_API_KEY
"""
from __future__ import annotations

import logging
import os
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


def _secretary_token() -> str:
    return (os.getenv("TBCC_SECRETARY_BOT_TOKEN") or os.getenv("SECRETARY_BOT_TOKEN") or "").strip()


def _payment_bot_username() -> str:
    u = (
        os.getenv("TBCC_PAYMENT_BOT_USERNAME")
        or os.getenv("BOT_USERNAME")
        or ""
    ).strip().lstrip("@")
    return u


def _rate_limit_per_minute() -> int:
    raw = (os.getenv("TBCC_SECRETARY_RATE_LIMIT_PER_MIN") or "20").strip()
    try:
        return max(1, min(120, int(raw)))
    except ValueError:
        return 20


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


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    pay = _payment_bot_username()
    pay_line = (
        f"Purchases, Stars invoices, and digital packs: @{pay}\n(open that bot and use /subscribe or /packs)"
        if pay
        else "Purchases run through the main payment bot — ask an admin for the link."
    )
    text = (
        "Hi — I'm the **AOF assistant**.\n\n"
        "Ask me about access, subscriptions, or how things work. "
        "I don't take payments in this chat.\n\n"
        + pay_line
    )
    await msg.reply_text(text, parse_mode="Markdown", **_reply_kwargs(msg))


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_subscribe_hint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    pay = _payment_bot_username()
    if not pay:
        await msg.reply_text("Payment bot username is not configured.", **_reply_kwargs(msg))
        return
    await msg.reply_text(
        f"Subscriptions (Stars + access) are handled here:\nhttps://t.me/{pay}\n\n"
        f"Open that chat and send **/subscribe**.",
        parse_mode="Markdown",
        **_reply_kwargs(msg),
    )


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    context.user_data.pop(HISTORY_KEY, None)
    await msg.reply_text("Conversation context cleared.", **_reply_kwargs(msg))


async def cmd_shop_hint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    pay = _payment_bot_username()
    if not pay:
        await msg.reply_text("Payment bot username is not configured.", **_reply_kwargs(msg))
        return
    await msg.reply_text(
        f"Storefront / promos:\nhttps://t.me/{pay}\n\nSend **/shop** in that bot.",
        parse_mode="Markdown",
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

    try:
        await context.bot.send_chat_action(
            chat_id=msg.chat_id, action=ChatAction.TYPING, **_reply_kwargs(msg)
        )
    except TypeError:
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
    except Exception as e:
        logger.debug("send_chat_action: %s", e)

    hist: list[dict[str, str]] = context.user_data.get(HISTORY_KEY) or []
    hist = [{"role": m["role"], "content": m["content"]} for m in hist if m.get("role") in ("user", "assistant", "system")]

    pay = _payment_bot_username()
    extra = ""
    if pay:
        extra = f"\n\nPayment bot for checkout (tell the user to open @{pay} for /subscribe, /packs, /shop)."

    catalog = await fetch_subscription_catalog_snippet(API_BASE)
    if catalog:
        extra = extra + "\n\n" + catalog

    messages: list[dict[str, str]] = [{"role": "system", "content": default_system_prompt()}]
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

    await msg.reply_text(reply[:4096], **_reply_kwargs(msg))

    next_hist = hist + [{"role": "user", "content": user_text}, {"role": "assistant", "content": reply}]
    max_keep = _history_max_messages()
    context.user_data[HISTORY_KEY] = next_hist[-max_keep:]


async def on_unsupported_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Voice/photo/etc. in private — short hint."""
    msg = update.effective_message
    if not msg or msg.chat.type != "private":
        return
    await msg.reply_text(
        "I can only read **text** in this version. Type your question, or use /help.",
        parse_mode="Markdown",
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
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & (~filters.COMMAND), on_private_text))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~filters.TEXT), on_unsupported_private))

    print("Secretary bot running. Commands: /start /help /subscribe /shop /reset")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
