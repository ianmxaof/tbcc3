"""
TBCC Macro Model Search bot — dedicated DM bot for /macrosearch and /macroaddsource.

Run from tbcc/backend:  python -m bots.macro_search_bot

Env:
  TBCC_MACRO_SEARCH_BOT_TOKEN (required)
  TBCC_API_URL — payment-bot-settings + macro source DB (default http://localhost:8000)
  ADMIN_TELEGRAM_ID — required for /macroaddsource
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from dotenv import load_dotenv

_env = Path(__file__).resolve().parent.parent.parent / ".env"
if _env.exists():
    load_dotenv(_env, override=True)

import httpx
from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from bots.macro_search_telegram import build_macro_search_handlers, cmd_macrosearch
from bots.macro_search_forum import build_forum_handlers

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

API_BASE = os.getenv("TBCC_API_URL", "http://localhost:8000").rstrip("/")
_runtime_cache: dict | None = None
_runtime_loaded_at: float = 0.0
_runtime_ttl_s = 30.0


def _token() -> str:
    return (os.getenv("TBCC_MACRO_SEARCH_BOT_TOKEN") or os.getenv("MACRO_SEARCH_BOT_TOKEN") or "").strip()


async def _get_runtime_settings(force_refresh: bool = False) -> dict:
    import time

    global _runtime_cache, _runtime_loaded_at
    now = time.monotonic()
    if not force_refresh and _runtime_cache is not None and (now - _runtime_loaded_at) < _runtime_ttl_s:
        return _runtime_cache
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{API_BASE}/payment-bot-settings", timeout=10.0)
            if r.is_success:
                payload = r.json()
                _runtime_cache = (payload.get("effective") if isinstance(payload, dict) else None) or {}
            else:
                _runtime_cache = _runtime_cache or {}
    except Exception as e:
        logger.warning("payment-bot-settings fetch failed: %s", e)
        _runtime_cache = _runtime_cache or {}
    if not _runtime_cache.get("macro_search_sources"):
        try:
            from app.services.model_search_engine import get_macro_search_sites

            _runtime_cache["macro_search_sources"] = get_macro_search_sites()
        except Exception:
            pass
    _runtime_loaded_at = now
    return _runtime_cache


async def _patch_macro_custom_sources(custom: list) -> bool:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.patch(
                f"{API_BASE}/payment-bot-settings",
                json={"macro_search_custom_sources": custom},
                timeout=15.0,
            )
            return r.is_success
    except Exception as e:
        logger.warning("patch macro_search_custom_sources failed: %s", e)
        return False


async def _force_refresh_runtime_settings() -> None:
    await _get_runtime_settings(force_refresh=True)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    from bots.macro_search_forum import forum_enabled, forum_welcome_html

    if forum_enabled() and update.effective_chat and update.effective_chat.type != "private":
        await msg.reply_text(forum_welcome_html(), parse_mode="HTML")
        return
    await msg.reply_text(
        "TBCC Macro Search\n\n"
        "• /macrosearch &lt;username&gt; — scan macro sources, send video URLs\n"
        "• /videofind — same as /macrosearch\n"
        "• /inbox &lt;url&gt; — queue erome/bunkr link for TBCC review\n"
        "• /suggestsource — suggest a macro search site (community review)\n"
        "• /macroaddsource — add a source immediately (admin)\n"
        "• /macrolist — list sources (admin)\n\n"
        "Deep link: /start ms_&lt;username&gt;",
        parse_mode="HTML",
    )


async def cmd_videofind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_macrosearch(update, context, get_settings=_get_runtime_settings)


async def _post_init(app: Application) -> None:
    commands = [
        BotCommand("start", "Help & commands"),
        BotCommand("help", "Commands & TBCC bridge help"),
        BotCommand("macrosearch", "Macro search by username"),
        BotCommand("videofind", "Alias for macrosearch"),
        BotCommand("inbox", "Queue gallery URL for TBCC"),
        BotCommand("suggestsource", "Suggest macro search site"),
        BotCommand("macroaddsource", "Add macro source (admin)"),
        BotCommand("macrodebug", "Per-source probe report (admin)"),
        BotCommand("macrolist", "List macro sources (admin)"),
        BotCommand("pending", "Pending submissions (admin)"),
    ]
    try:
        await app.bot.set_my_commands(commands)
    except Exception as e:
        logger.warning("set_my_commands failed: %s", e)
    from bots.macro_search_forum import post_forum_welcome

    await post_forum_welcome(app)


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
    """Build macro_search Application without polling (Zeus co-host ready)."""
    tok = (token if token is not None else _token()).strip()
    if not tok:
        return None

    t = _telegram_http_timeout_seconds()
    b = (
        Application.builder()
        .token(tok)
        .post_init(_post_init)
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

    from bots.macro_search_forum import forum_enabled
    from telegram.ext import filters

    dm_scope = filters.ChatType.PRIVATE if forum_enabled() else None

    app.add_handler(CommandHandler("videofind", cmd_videofind, filters=dm_scope))

    async def start_deeplink(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args or []
        payload = args[0] if args else ""
        if payload.startswith("ms_") or payload.startswith("vf_"):
            from bots.macro_search_telegram import normalize_macro_username

            username = normalize_macro_username(payload[3:])
            if username:
                context.args = [username]
                await cmd_macrosearch(update, context, get_settings=_get_runtime_settings)
                return
        await cmd_start(update, context)

    app.add_handler(CommandHandler("start", start_deeplink))

    for h in build_macro_search_handlers(
        _get_runtime_settings,
        _patch_macro_custom_sources,
        _force_refresh_runtime_settings,
        command_filters=dm_scope,
    ):
        app.add_handler(h)

    for h in build_forum_handlers(_get_runtime_settings, _patch_macro_custom_sources):
        app.add_handler(h)

    return app


def main() -> None:
    app = build_application()
    if app is None:
        print("Set TBCC_MACRO_SEARCH_BOT_TOKEN in tbcc/.env — see .env.example")
        return

    br = _telegram_bootstrap_retries()
    print(
        "Macro search bot running. Commands: /start, /macrosearch, /inbox, /suggestsource, "
        "/macroaddsource, forum topic bridge (see TBCC_MACRO_SEARCH_FORUM_* env)"
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=br)


if __name__ == "__main__":
    main()
