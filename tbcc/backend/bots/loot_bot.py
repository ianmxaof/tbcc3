"""
AOF Loot Overseer (@aof_lootgod_bot) — TBCC Telegram Bot Command Center integration.

- Token resolution: if `TBCC_INTERNAL_API_KEY` is set, tries `GET /loot-bot-settings/internal-runtime` first;
  on any connection/HTTP failure, falls back to `TBCC_LOOT_BOT_TOKEN` in tbcc/.env (so the bot can start
  before the API is up, or when the API is on a different host).
- Polls `GET /loot-bot-settings` on an interval for invite URL, username, narrative flags, etc.

Run from tbcc/backend:  python -m bots.loot_bot

Requires: TBCC_API_URL if the API is not http://localhost:8000
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
import sys
import time
from pathlib import Path

_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from dotenv import load_dotenv

_env = Path(__file__).resolve().parent.parent.parent / ".env"
if _env.exists():
    load_dotenv(_env, override=True)

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

API_BASE = os.getenv("TBCC_API_URL", "http://localhost:8000").rstrip("/")

# Longer read timeout + retries: API may be restarting (uvicorn reload) or Windows may hit transient socket limits.
_HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=45.0, write=10.0, pool=5.0)
_SETTINGS_HTTP_ATTEMPTS = max(1, int(os.getenv("TBCC_LOOT_SETTINGS_HTTP_ATTEMPTS", "3")))


def _telegram_http_timeout_seconds() -> float:
    """PTB defaults can be too short on unstable networks; clamp to sane range."""
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


def _get_with_retries(url: str, *, headers: dict[str, str] | None = None) -> httpx.Response:
    for attempt in range(_SETTINGS_HTTP_ATTEMPTS):
        try:
            with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
                return client.get(url, headers=headers or {})
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError) as e:
            if attempt + 1 < _SETTINGS_HTTP_ATTEMPTS:
                wait = 2.0 * (attempt + 1)
                logger.warning(
                    "TBCC GET %s failed (%s), retry %s/%s in %.0fs",
                    url,
                    e,
                    attempt + 1,
                    _SETTINGS_HTTP_ATTEMPTS,
                    wait,
                )
                time.sleep(wait)
            else:
                raise


def _fetch_public_effective() -> dict:
    r = _get_with_retries(f"{API_BASE}/loot-bot-settings")
    r.raise_for_status()
    data = r.json()
    return data.get("effective") or {}


def _fetch_token_internal() -> str | None:
    key = (os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()
    if not key:
        return None
    try:
        r = _get_with_retries(
            f"{API_BASE}/loot-bot-settings/internal-runtime",
            headers={"X-TBCC-Internal-Key": key},
        )
        if r.status_code != 200:
            logger.warning("internal-runtime HTTP %s — falling back to env token", r.status_code)
            return None
        token = (r.json().get("bot_token") or "").strip()
        return token or None
    except httpx.RequestError as e:
        logger.warning(
            "Could not reach TBCC at %s for internal-runtime (%s) — using TBCC_LOOT_BOT_TOKEN if set",
            API_BASE,
            e,
        )
        return None


def resolve_bot_token() -> str:
    t = _fetch_token_internal()
    if t:
        logger.info("Using bot token from TBCC internal-runtime (dashboard or merged env)")
        return t
    t = (os.getenv("TBCC_LOOT_BOT_TOKEN") or "").strip()
    if t:
        logger.info("Using TBCC_LOOT_BOT_TOKEN from environment")
        return t
    logger.error(
        "No token: set TBCC_LOOT_BOT_TOKEN in tbcc/.env, or store token in dashboard Bots → Loot overseer "
        "and set TBCC_INTERNAL_API_KEY so this process can fetch /loot-bot-settings/internal-runtime."
    )
    raise SystemExit(2)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data.get("effective") or {}
    invite = cfg.get("primary_loot_room_invite_url") or "https://t.me/+97f4Crv3G1RkMGU5"
    un = cfg.get("bot_username") or "aof_lootgod_bot"
    spoiler = cfg.get("drop_spoiler_default", True)
    lines = [
        "<b>AOF Loot Overseer</b>",
        f"Bot: @{html.escape(str(un))}",
        "",
        "<b>Primary loot room</b> (assign media pools in TBCC; eligibility in <code>loot_pool_eligibility</code>):",
        f'<a href="{html.escape(str(invite), quote=True)}">Open invite link</a>',
        "",
        f"Album spoiler default: <code>{'on' if spoiler else 'off'}</code> (from TBCC)",
        "",
        "Drop orchestration will attach here; settings refresh from the TBCC API on a timer.",
    ]
    await update.effective_message.reply_html("\n".join(lines), disable_web_page_preview=False)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data.get("effective") or {}
    lines = [
        "<b>Loot overseer status</b>",
        f"API: <code>{html.escape(API_BASE)}</code>",
        f"User-facing token: <code>{html.escape(str(cfg.get('bot_token_masked') or 'n/a'))}</code>",
        f"Token source: <code>{html.escape(str(cfg.get('bot_token_source') or '?'))}</code>",
        f"Narrative LLM layer: <code>{'on' if cfg.get('narrative_enabled') else 'off'}</code>",
    ]
    await update.effective_message.reply_html("\n".join(lines))


async def _poll_settings(application: Application) -> None:
    while True:
        cfg = application.bot_data.get("effective") or {}
        try:
            interval = float(cfg.get("config_poll_seconds") or 30)
        except (TypeError, ValueError):
            interval = 30.0
        interval = max(5.0, min(interval, 3600.0))
        await asyncio.sleep(interval)
        try:
            application.bot_data["effective"] = await asyncio.to_thread(_fetch_public_effective)
            logger.debug("Loot bot settings refreshed from TBCC")
        except httpx.HTTPError as e:
            logger.warning("Loot bot settings refresh failed (%s) — keeping previous config", e)
        except Exception:
            logger.exception("Loot bot settings refresh failed")


async def post_init(application: Application) -> None:
    try:
        application.bot_data["effective"] = await asyncio.to_thread(_fetch_public_effective)
    except Exception:
        logger.exception("Initial loot settings fetch failed — using defaults until next poll")
        application.bot_data["effective"] = {}
    asyncio.create_task(_poll_settings(application))


def main() -> None:
    token = resolve_bot_token()
    t = _telegram_http_timeout_seconds()
    br = _telegram_bootstrap_retries()
    application = (
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
        .build()
    )
    proxy = os.getenv("TELEGRAM_PROXY", "").strip()
    if proxy:
        application = (
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
            .proxy(proxy)
            .build()
        )
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("status", cmd_status))
    logger.info(
        "Loot overseer starting (API %s), Telegram timeout=%.1fs, bootstrap_retries=%s%s",
        API_BASE,
        t,
        br,
        f", proxy={proxy}" if proxy else "",
    )
    application.run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=br)


if __name__ == "__main__":
    main()
