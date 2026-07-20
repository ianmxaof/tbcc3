"""
Generic Telegram ↔ LLM bridge (private DMs).

Use for any persona you define in TBCC_LLM_CHAT_SYSTEM_PROMPT. Default provider is local Ollama.

Run: cd tbcc/backend && python -m bots.llm_chat_bot

Env:
  TBCC_LLM_CHAT_BOT_TOKEN (required)
  TBCC_LLM_CHAT_PROVIDER=ollama | openai
  TBCC_OLLAMA_BASE_URL=http://127.0.0.1:11434  TBCC_OLLAMA_MODEL=llama3.2
  TBCC_LLM_CHAT_SYSTEM_PROMPT=...  (operator-defined persona)
  TBCC_LLM_CHAT_RATE_LIMIT_PER_MIN, TBCC_LLM_CHAT_HISTORY_MAX_MESSAGES
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

from app.services.llm_chat import (
    complete_llm_chat,
    default_system_prompt,
    provider_configured,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

HISTORY_KEY = "llm_chat_history"

_rate_log: dict[int, deque[float]] = {}


def _token() -> str:
    return (os.getenv("TBCC_LLM_CHAT_BOT_TOKEN") or os.getenv("LLM_CHAT_BOT_TOKEN") or "").strip()


def _rate_limit_per_minute() -> int:
    raw = (os.getenv("TBCC_LLM_CHAT_RATE_LIMIT_PER_MIN") or "30").strip()
    try:
        return max(1, min(120, int(raw)))
    except ValueError:
        return 30


def _history_max() -> int:
    raw = (os.getenv("TBCC_LLM_CHAT_HISTORY_MAX_MESSAGES") or "24").strip()
    try:
        return max(2, min(48, int(raw)))
    except ValueError:
        return 24


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


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    prov = (os.getenv("TBCC_LLM_CHAT_PROVIDER") or "ollama").strip().lower()
    text = (
        "<b>LLM chat</b>\n\n"
        "Send a message and I will reply using your configured model.\n\n"
        f"<b>Provider</b>: <code>{prov}</code>\n"
        "Commands: /help · /reset (clear memory)\n\n"
        "Persona is set on the server via <code>TBCC_LLM_CHAT_SYSTEM_PROMPT</code>."
    )
    await msg.reply_text(text, parse_mode="HTML")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    context.user_data.pop(HISTORY_KEY, None)
    await msg.reply_text("Conversation cleared.")


async def on_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or not msg.text:
        return
    if msg.chat.type != "private":
        return

    if not _allow_rate_limit(user.id):
        await msg.reply_text("Slow down — rate limit. Try again in a minute.")
        return

    if not provider_configured():
        await msg.reply_text(
            "LLM not configured. For OpenAI set TBCC_OPENAI_API_KEY; for Ollama run "
            "`ollama serve` and `ollama pull <model>`."
        )
        return

    user_text = msg.text.strip()
    if not user_text:
        return

    try:
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
    except Exception as e:
        logger.debug("send_chat_action: %s", e)

    hist: list[dict[str, str]] = context.user_data.get(HISTORY_KEY) or []
    hist = [m for m in hist if m.get("role") in ("user", "assistant", "system") and m.get("content")]

    messages: list[dict[str, str]] = [{"role": "system", "content": default_system_prompt()}]
    messages.extend(hist[-_history_max() :])
    messages.append({"role": "user", "content": user_text})

    try:
        reply = await complete_llm_chat(messages)
    except Exception as e:
        logger.warning("llm_chat failed: %s", e)
        await msg.reply_text(f"Model error: {e!s}"[:4000])
        return

    await msg.reply_text((reply or "")[:4096])

    next_hist = hist + [{"role": "user", "content": user_text}, {"role": "assistant", "content": reply}]
    max_keep = _history_max() * 2 + 4
    context.user_data[HISTORY_KEY] = next_hist[-max_keep:]


async def post_init(app: Application) -> None:
    me = await app.bot.get_me()
    logger.info("llm_chat bot online @%s id=%s", me.username, me.id)
    commands = [
        BotCommand("start", "Intro"),
        BotCommand("help", "Intro"),
        BotCommand("reset", "Clear conversation memory"),
    ]
    try:
        await app.bot.set_my_commands(commands)
    except Exception as e:
        logger.warning("set_my_commands: %s", e)


def build_application(token: str | None = None) -> Application | None:
    """Build the LLM-chat Application without starting a poller (Zeus co-host ready)."""
    tok = (token if token is not None else _token()).strip()
    if not tok:
        return None
    app = Application.builder().token(tok).post_init(post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(
        MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & (~filters.COMMAND), on_private_text)
    )
    return app


def main() -> None:
    app = build_application()
    if app is None:
        print("Set TBCC_LLM_CHAT_BOT_TOKEN (or LLM_CHAT_BOT_TOKEN) in tbcc/.env")
        return

    print("LLM chat bot running. Commands: /start /help /reset")
    print("Provider:", (os.getenv("TBCC_LLM_CHAT_PROVIDER") or "ollama").strip())
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
