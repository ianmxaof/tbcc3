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
import traceback
from pathlib import Path

_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from dotenv import load_dotenv

_env = Path(__file__).resolve().parent.parent.parent / ".env"
if _env.exists():
    load_dotenv(_env, override=True)

import httpx
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonCommands,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction, ChatType
from telegram.error import Conflict, Forbidden, NetworkError, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bots.error_reporter import report_bot_error

from app.services.loot_inline_keyboards import roll_action_label
from app.services.loot_roll_presentation import pick_loading_status_line

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

API_BASE = os.getenv("TBCC_API_URL", "http://localhost:8000").rstrip("/")


def _loading_status_line() -> str:
    return pick_loading_status_line()

# Longer read timeout + retries: API may be restarting (uvicorn reload) or Windows may hit transient socket limits.
_HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=45.0, write=10.0, pool=5.0)
# Free-pull delivery runs Telethon in the API — allow long reads (matches _run_loot_async 300s cap).
_LOOT_CLAIM_TIMEOUT = httpx.Timeout(connect=15.0, read=300.0, write=30.0, pool=5.0)
_SETTINGS_HTTP_ATTEMPTS = max(1, int(os.getenv("TBCC_LOOT_SETTINGS_HTTP_ATTEMPTS", "3")))

_DEFAULT_PAYMENT_BOT_USERNAME = "aofsubscriptions_bot"

# Reply keyboard labels → action key
_LOOT_KEYBOARD: dict[str, str] = {
    "🎲 Claim free pull": "roll",
    "📖 Guide": "guide",
    "🔗 Referral link": "referral",
    "🗝 24h Loot Room keys": "loot_keys",
    "📦 Creator promo": "model",
}


def _payment_bot_username() -> str:
    return (
        os.getenv("TBCC_PAYMENT_BOT_USERNAME")
        or os.getenv("BOT_USERNAME")
        or _DEFAULT_PAYMENT_BOT_USERNAME
    ).strip().lstrip("@")


def _loot_reply_keyboard() -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(label)] for label in _LOOT_KEYBOARD]
    rows.append([KeyboardButton("💬 Ask the Overseer")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


def _loot_inline_keyboard(
    cfg: dict,
    *,
    free_pull_number: int = 0,
    free_pulls_remaining: int | None = None,
    free_pull_limit: int = 5,
    rarity_tier: int = 0,
) -> InlineKeyboardMarkup:
    invite = (cfg.get("primary_loot_room_invite_url") or os.getenv("TBCC_LOOT_ROOM_INVITE_URL") or "").strip()
    pay = _payment_bot_username()
    pay_safe = html.escape(pay) if pay else ""
    rows: list[list[InlineKeyboardButton]] = []
    if pay:
        rows.append(
            [
                InlineKeyboardButton("🗝 24h room key", url=f"https://t.me/{pay_safe}?start=loot"),
                InlineKeyboardButton("💳 Payment bot", url=f"https://t.me/{pay_safe}"),
            ]
        )
    roll_text = roll_action_label(
        free_pull_number=free_pull_number,
        free_pulls_remaining=free_pulls_remaining,
        free_pull_limit=free_pull_limit,
    )
    rows.append(
        [
            InlineKeyboardButton(roll_text, callback_data="loot:roll"),
            InlineKeyboardButton("🔗 Referral", callback_data="loot:referral"),
        ],
    )
    from app.services.loot_inline_keyboards import (
        free_pull_midpoint_upsell_row,
        should_show_free_pull_midpoint,
    )

    if should_show_free_pull_midpoint(
        free_pull_number=free_pull_number,
        free_pulls_remaining=free_pulls_remaining,
    ):
        midpoint = free_pull_midpoint_upsell_row(payment_bot_username=pay)
        if midpoint:
            rows.append(midpoint)
    rows.append(
        [
            InlineKeyboardButton("📖 Guide", callback_data="loot:guide"),
            InlineKeyboardButton("🌐 Network", callback_data="aof_net:home"),
        ]
    )
    if invite:
        rows.append([InlineKeyboardButton("🚪 Loot Room (paid key required)", url=invite)])
    if int(rarity_tier or 0) >= 7 and pay:
        rows.append(
            [InlineKeyboardButton("⭐ VIP from $10", url=f"https://t.me/{pay}?start=subscribe")]
        )
    return InlineKeyboardMarkup(rows)


async def _safe_reply_html(msg, text: str, **kwargs):
    """Reply with HTML; return Message or None if user blocked the bot or chat is unreachable."""
    try:
        return await msg.reply_html(text, **kwargs)
    except Forbidden:
        logger.info("Cannot reply — user blocked the bot or chat forbidden (chat_id=%s)", getattr(msg, "chat_id", "?"))
        return None
    except TelegramError as e:
        logger.warning("Telegram reply failed: %s", e)
        return None


async def _drop_transient_msg(msg) -> None:
    if msg is None:
        return
    try:
        await msg.delete()
    except TelegramError:
        pass


async def _send_welcome(msg, context: ContextTypes.DEFAULT_TYPE, cfg: dict | None = None) -> None:
    cfg = cfg or context.application.bot_data.get("effective") or {}
    if msg.chat and msg.chat.type != ChatType.PRIVATE:
        from app.services.loot_dm_guard import loot_dm_redirect_html, loot_dm_redirect_markup, should_redirect_loot_to_dm

        if should_redirect_loot_to_dm(chat_type=str(msg.chat.type)):
            bot_un = _loot_bot_username(cfg)
            await _safe_reply_html(
                msg,
                loot_dm_redirect_html(bot_username=bot_un),
                disable_web_page_preview=True,
                reply_markup=loot_dm_redirect_markup(bot_username=bot_un),
            )
            return
    pay = _payment_bot_username()
    lines = [
        "<b>Loot Overseer</b>",
        "",
        "Tap <b>Roll now</b> — your first pull includes a fast welcome and teaches the table.",
        "Five complimentary pulls (nerfed taste); paid 24h runs unlock the full ladder.",
        "",
        f"Keys: @{html.escape(pay)} → /loot" if pay else "Keys: payment bot /loot",
        "Tap <b>📖 Guide</b> anytime for the full summary.",
    ]
    ok = await _safe_reply_html(
        msg,
        "\n".join(lines),
        disable_web_page_preview=False,
        reply_markup=_loot_inline_keyboard(cfg),
    )
    if ok is not None:
        try:
            await msg.reply_text("Quick actions:", reply_markup=_loot_reply_keyboard())
        except TelegramError as e:
            logger.debug("loot reply keyboard: %s", e)


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


def _token_valid_for_telegram(token: str) -> bool:
    try:
        r = httpx.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=15.0,
        )
        if r.status_code != 200:
            return False
        data = r.json()
        return bool(data.get("ok"))
    except httpx.HTTPError:
        return False


def resolve_bot_token() -> str:
    runtime_t = _fetch_token_internal()
    env_t = (os.getenv("TBCC_LOOT_BOT_TOKEN") or "").strip()
    for label, t in (
        ("TBCC internal-runtime (dashboard)", runtime_t),
        ("TBCC_LOOT_BOT_TOKEN", env_t),
    ):
        if not t:
            continue
        if _token_valid_for_telegram(t):
            logger.info("Using bot token from %s", label)
            return t
        logger.warning(
            "Token from %s failed Telegram getMe — trying next source",
            label,
        )
    if runtime_t and env_t and runtime_t != env_t:
        logger.error(
            "Dashboard token and TBCC_LOOT_BOT_TOKEN are both invalid. "
            "Fix Bots → Loot overseer token or update tbcc/.env."
        )
    else:
        logger.error(
            "No valid token: set TBCC_LOOT_BOT_TOKEN in tbcc/.env, or store a valid token in "
            "dashboard Bots → Loot overseer with TBCC_INTERNAL_API_KEY for internal-runtime."
        )
    raise SystemExit(2)


def _internal_headers() -> dict[str, str]:
    key = (os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()
    return {"X-TBCC-Internal-Key": key} if key else {}


def _api_post_sync(path: str, *, json_body: dict | None = None, params: dict | None = None) -> httpx.Response:
    url = f"{API_BASE}{path}"
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        return client.post(url, json=json_body, params=params, headers=_internal_headers())


def _api_get_sync(path: str, *, params: dict | None = None) -> httpx.Response:
    url = f"{API_BASE}{path}"
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        return client.get(url, params=params, headers=_internal_headers())


async def _record_loot_referral(referred_user_id: int, referrer_code: str) -> bool:
    try:
        r = await asyncio.to_thread(
            _api_post_sync,
            "/loot/referrals/record",
            json_body={
                "referred_user_id": int(referred_user_id),
                "referrer_code": referrer_code.strip().upper(),
            },
        )
        return r.status_code == 200 and bool((r.json() or {}).get("ok"))
    except Exception:
        logger.exception("loot referral record failed")
        return False


async def _fetch_referral_status(telegram_user_id: int) -> dict | None:
    try:
        r = await asyncio.to_thread(
            _api_get_sync,
            "/loot/referrals/status",
            params={"telegram_user_id": int(telegram_user_id)},
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        logger.exception("loot referral status failed")
    return None


async def _submit_creator_url(
    telegram_user_id: int,
    url: str,
    *,
    display_name: str | None = None,
) -> dict:
    body: dict = {"url": url.strip(), "telegram_user_id": int(telegram_user_id)}
    if display_name:
        body["display_name"] = display_name.strip()
    r = await asyncio.to_thread(
        _api_post_sync,
        "/loot/creator-submit",
        json_body=body,
    )
    if r.status_code >= 400:
        detail = r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else r.text
        return {"ok": False, "detail": detail}
    data = r.json()
    data["ok"] = True
    return data


def _key_roll_status(telegram_user_id: int) -> dict | None:
    """GET /loot/key-roll/status — decide free vs paid claim path."""
    try:
        r = _api_get_sync(
            "/loot/key-roll/status",
            params={"telegram_user_id": int(telegram_user_id)},
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        logger.exception("loot key-roll status failed")
    return None


def _claim_key_roll(telegram_user_id: int) -> dict:
    """POST /loot/key-roll/claim — full paid-key roll (sync httpx; run via to_thread)."""
    url = f"{API_BASE}/loot/key-roll/claim"
    params = {"telegram_user_id": int(telegram_user_id)}
    headers: dict[str, str] = {}
    key = (os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()
    if key:
        headers["X-TBCC-Internal-Key"] = key
    attempts = max(1, int(os.getenv("TBCC_LOOT_CLAIM_HTTP_ATTEMPTS", "3")))
    last_err: Exception | None = None
    for attempt in range(attempts):
        try:
            with httpx.Client(timeout=_LOOT_CLAIM_TIMEOUT) as client:
                r = client.post(url, params=params, headers=headers)
            if r.status_code == 403:
                detail = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                return {"ok": False, "not_key_holder": True, "detail": detail}
            if r.status_code == 400:
                try:
                    detail = r.json()
                except Exception:
                    detail = r.text
                return {"ok": False, "detail": detail, "http_status": 400}
            r.raise_for_status()
            return r.json()
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError) as e:
            last_err = e
            if attempt + 1 < attempts:
                wait = 2.0 * (attempt + 1)
                logger.warning(
                    "loot key-roll POST failed (%s), retry %s/%s in %.0fs",
                    e,
                    attempt + 1,
                    attempts,
                    wait,
                )
                time.sleep(wait)
            else:
                raise
    if last_err:
        raise last_err
    raise RuntimeError("loot key-roll: no response")


def _claim_free_pull(telegram_user_id: int) -> dict:
    """POST /loot/free-pull/claim — delivers pull to user DM (sync httpx; run via to_thread)."""
    url = f"{API_BASE}/loot/free-pull/claim"
    params = {"telegram_user_id": int(telegram_user_id)}
    headers: dict[str, str] = {}
    key = (os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()
    if key:
        headers["X-TBCC-Internal-Key"] = key
    attempts = max(1, int(os.getenv("TBCC_LOOT_CLAIM_HTTP_ATTEMPTS", "3")))
    last_err: Exception | None = None
    for attempt in range(attempts):
        try:
            with httpx.Client(timeout=_LOOT_CLAIM_TIMEOUT) as client:
                r = client.post(url, params=params, headers=headers)
            if r.status_code == 403:
                return {"ok": False, "exhausted": True, "detail": r.json()}
            r.raise_for_status()
            return r.json()
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError) as e:
            last_err = e
            if attempt + 1 < attempts:
                wait = 2.0 * (attempt + 1)
                logger.warning(
                    "loot claim POST failed (%s), retry %s/%s in %.0fs",
                    e,
                    attempt + 1,
                    attempts,
                    wait,
                )
                time.sleep(wait)
            else:
                raise
    if last_err:
        raise last_err
    raise RuntimeError("loot claim: no response")


def _claim_vip_daily_pull(telegram_user_id: int) -> dict:
    """POST /loot/vip-daily-pull/claim — VIP daily god roll."""
    url = f"{API_BASE}/loot/vip-daily-pull/claim"
    params = {"telegram_user_id": int(telegram_user_id)}
    headers: dict[str, str] = {}
    key = (os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()
    if key:
        headers["X-TBCC-Internal-Key"] = key
    with httpx.Client(timeout=_LOOT_CLAIM_TIMEOUT) as client:
        r = client.post(url, params=params, headers=headers)
    if r.status_code == 403:
        return {"ok": False, "forbidden": True, "detail": r.json()}
    r.raise_for_status()
    return r.json()


def _claim_daily_pull(telegram_user_id: int) -> dict:
    """POST /loot/daily-pull/claim — free daily return pull."""
    url = f"{API_BASE}/loot/daily-pull/claim"
    params = {"telegram_user_id": int(telegram_user_id)}
    headers: dict[str, str] = {}
    key = (os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()
    if key:
        headers["X-TBCC-Internal-Key"] = key
    with httpx.Client(timeout=_LOOT_CLAIM_TIMEOUT) as client:
        r = client.post(url, params=params, headers=headers)
    if r.status_code == 403:
        return {"ok": False, "forbidden": True, "detail": r.json()}
    r.raise_for_status()
    return r.json()


async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Free daily return pull — /daily."""
    user = update.effective_user
    if not user:
        return
    msg = update.effective_message
    if not msg and update.callback_query:
        msg = update.callback_query.message
    if not msg:
        return

    if update.callback_query:
        try:
            await update.callback_query.answer("Pulling…")
        except TelegramError:
            pass
    try:
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.UPLOAD_PHOTO)
    except TelegramError:
        pass

    status_msg = await _safe_reply_html(msg, "<i>Dealing your daily pull…</i>", disable_web_page_preview=True)
    try:
        result = await asyncio.to_thread(_claim_daily_pull, int(user.id))
    except Exception as e:
        logger.warning("daily pull claim error: %s", e)
        await _drop_transient_msg(status_msg)
        await _safe_reply_html(
            msg,
            "<b>Daily pull failed</b>\nAPI unreachable — retry /daily in a few seconds.",
            disable_web_page_preview=True,
        )
        return

    await _drop_transient_msg(status_msg)
    if result.get("ok"):
        prev = result.get("preview") or {}
        delivery = result.get("delivery") or {}
        if int(delivery.get("media_sent") or 0) > 0:
            streak = int(prev.get("streak_days") or 1)
            every = int(prev.get("streak_bonus_every") or 0)
            bonus = int(prev.get("bonus_free_pulls_awarded") or 0)
            lines = [f"<b>Daily pull dealt</b> — day {streak} streak."]
            if bonus:
                lines.append("<b>Streak paid: +1 full free pull.</b> Burn it on /roll.")
            elif every:
                left = (every - (streak % every)) % every
                if left:
                    lines.append(f"<i>{left} more day{'s' if left != 1 else ''} → +1 full free pull.</i>")
            lines.append("<i>Resets 00:00 UTC. Miss a day and the streak restarts.</i>")
            await _safe_reply_html(msg, "\n".join(lines), disable_web_page_preview=True)
        return

    if result.get("forbidden"):
        detail = result.get("detail") or {}
        body = detail.get("detail") if isinstance(detail, dict) else detail
        if isinstance(body, dict):
            message = body.get("message") or "Daily pull unavailable."
            streak = body.get("streak_days")
            extra = f"\n<i>Streak: {int(streak)} day(s).</i>" if streak else ""
            await _safe_reply_html(
                msg,
                f"<b>{html.escape(str(message))}</b>{extra}",
                disable_web_page_preview=True,
            )
        return

    await _safe_reply_html(msg, "<b>Daily pull failed.</b> Try again later.", disable_web_page_preview=True)


async def cmd_viproll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """VIP subscriber daily god roll — /viproll."""
    user = update.effective_user
    if not user:
        return
    msg = update.effective_message
    if not msg and update.callback_query:
        msg = update.callback_query.message
    if not msg:
        return

    if update.callback_query:
        try:
            await update.callback_query.answer("God rolling…")
        except TelegramError:
            pass
    try:
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.UPLOAD_PHOTO)
    except TelegramError:
        pass

    status_msg = await _safe_reply_html(msg, "<i>Dealing your VIP god roll…</i>", disable_web_page_preview=True)
    try:
        result = await asyncio.to_thread(_claim_vip_daily_pull, int(user.id))
    except Exception as e:
        logger.warning("vip daily pull claim error: %s", e)
        await _drop_transient_msg(status_msg)
        await _safe_reply_html(
            msg,
            "<b>God roll failed</b>\nAPI unreachable — retry /viproll in a few seconds.",
            disable_web_page_preview=True,
        )
        return

    await _drop_transient_msg(status_msg)
    if result.get("ok"):
        prev = result.get("preview") or {}
        delivery = result.get("delivery") or {}
        tier = prev.get("rarity_tier") or "?"
        if int(delivery.get("media_sent") or 0) > 0:
            await _safe_reply_html(
                msg,
                f"<b>VIP god roll dealt</b> — tier {html.escape(str(tier))}.\n"
                "<i>One per day — back tomorrow for another.</i>",
                disable_web_page_preview=True,
            )
        return

    if result.get("forbidden"):
        detail = result.get("detail") or {}
        body = detail.get("detail") if isinstance(detail, dict) else detail
        if isinstance(body, dict):
            reason = body.get("reason") or ""
            message = body.get("message") or "VIP god roll unavailable."
            pay = body.get("payment_link") or ""
            extra = f'\n<a href="{html.escape(str(pay), quote=True)}">Get AOF VIP</a>' if pay else ""
            await _safe_reply_html(
                msg,
                f"<b>{html.escape(message)}</b>{extra}",
                disable_web_page_preview=True,
            )
        return

    await _safe_reply_html(msg, "<b>God roll failed.</b> Try again later.", disable_web_page_preview=True)


async def cmd_roll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    if await _redirect_loot_to_dm(update, context):
        return
    msg = update.effective_message
    if not msg and update.callback_query:
        msg = update.callback_query.message
    if not msg:
        return

    if update.callback_query:
        try:
            await update.callback_query.answer("Rolling…")
        except TelegramError:
            pass
    try:
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.UPLOAD_PHOTO)
    except TelegramError:
        pass

    cfg = context.application.bot_data.get("effective") or {}
    status_msg = await _safe_reply_html(
        msg,
        f"<i>{html.escape(_loading_status_line())}</i>",
        disable_web_page_preview=True,
    )

    try:
        # Status-first: never call key-roll for free-only users (avoids 500/403 noise
        # blocking the free-pull path when the API misbehaves on paid claim).
        status = await asyncio.to_thread(_key_roll_status, int(user.id))
        if status and status.get("can_key_roll"):
            result = await asyncio.to_thread(_claim_key_roll, int(user.id))
            if result.get("not_key_holder"):
                result = await asyncio.to_thread(_claim_free_pull, int(user.id))
            elif not result.get("ok"):
                result = await asyncio.to_thread(_claim_free_pull, int(user.id))
            elif int((result.get("delivery") or {}).get("media_sent") or 0) <= 0:
                result = await asyncio.to_thread(_claim_free_pull, int(user.id))
        else:
            result = await asyncio.to_thread(_claim_free_pull, int(user.id))
    except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError) as e:
        logger.warning("roll claim transient API error: %s", e)
        await _drop_transient_msg(status_msg)
        await _safe_reply_html(
            msg,
            "<b>TBCC is catching up</b>\nThe API was briefly unreachable — tap <b>/roll</b> again in a few seconds.",
            disable_web_page_preview=True,
            reply_markup=_loot_inline_keyboard(context.application.bot_data.get("effective") or {}),
        )
        return
    except httpx.HTTPStatusError as e:
        # Paid claim blew up but user may still have free pulls — one recovery attempt.
        if e.response is not None and e.response.status_code >= 500:
            try:
                result = await asyncio.to_thread(_claim_free_pull, int(user.id))
            except Exception:
                result = None
            if result and result.get("ok"):
                pass  # fall through to success handling
            else:
                await _drop_transient_msg(status_msg)
                await _safe_reply_html(
                    msg,
                    f"<b>Pull failed</b>\n<code>{html.escape(str(e))}</code>",
                    disable_web_page_preview=True,
                    reply_markup=_loot_inline_keyboard(context.application.bot_data.get("effective") or {}),
                )
                return
        else:
            await _drop_transient_msg(status_msg)
            detail = ""
            if e.response is not None:
                try:
                    body = e.response.json()
                    detail = str(body.get("detail") or body)
                except Exception:
                    detail = (e.response.text or str(e))[:400]
            else:
                detail = str(e)
            friendly = detail
            if "No approved media candidates" in detail:
                friendly = (
                    "Loot pool is empty — no deliverable media on the island right now. "
                    "TBCC ops is refilling; try again in a few minutes."
                )
            await _safe_reply_html(
                msg,
                f"<b>Pull failed</b>\n{html.escape(friendly)}",
                disable_web_page_preview=True,
                reply_markup=_loot_inline_keyboard(context.application.bot_data.get("effective") or {}),
            )
            return
    except Exception:
        logger.exception("roll claim failed")
        await _drop_transient_msg(status_msg)
        await _safe_reply_html(
            msg,
            "<b>Pull failed</b>\nAPI unreachable — is TBCC backend running?",
            disable_web_page_preview=True,
            reply_markup=_loot_inline_keyboard(context.application.bot_data.get("effective") or {}),
        )
        return

    await _drop_transient_msg(status_msg)
    cfg = context.application.bot_data.get("effective") or {}

    if result.get("ok") and (result.get("roll_kind") == "key_roll" or (result.get("preview") or {}).get("roll_kind") == "key_roll"):
        prev = result.get("preview") or {}
        delivery = result.get("delivery") or {}
        media_sent = int(delivery.get("media_sent") or 0)
        tier = int(prev.get("rarity_tier") or 0)
        mods = int(prev.get("modifier_slot_count") or 0)
        finale_markup = _loot_inline_keyboard(cfg, rarity_tier=tier)
        if media_sent <= 0:
            notes = ", ".join(str(x) for x in (delivery.get("notes") or []) if "skip" in str(x).lower())
            from app.services.loot_user_errors import loot_delivery_failed_user_html

            await _safe_reply_html(
                msg,
                loot_delivery_failed_user_html(
                    headline="Key roll failed — no loot delivered.",
                    technical_note=notes[:350] or "media load failed",
                ),
                disable_web_page_preview=True,
                reply_markup=finale_markup,
            )
            return
        card_ok = bool(result.get("tier_card_delivered") or delivery.get("tier_card_delivered"))
        comp = result.get("key_compensation") or {}
        comp_line = ""
        if not card_ok and comp.get("ok"):
            comp_line = (
                "\n\n<b>Card reveal missed — your Loot Room key was extended 24h.</b>"
                f"\n<i>New expiry: {html.escape(str(comp.get('extended_until') or 'updated'))}</i>"
            )
        elif not card_ok:
            comp_line = (
                "\n\n<b>Card reveal missed this pull.</b> Tap <b>/roll</b> again — your key time was not consumed."
            )
        await _safe_reply_html(
            msg,
            f"<b>Key roll dealt.</b>\n"
            f"Tier <b>{tier}</b> · {mods} modifier slot(s).\n"
            "<i>Your Loot Room key unlocked the full ladder.</i>"
            f"{comp_line}",
            disable_web_page_preview=True,
            reply_markup=finale_markup,
        )
        return

    if result.get("ok"):
        prev = result.get("preview") or {}
        delivery = result.get("delivery") or {}
        media_sent = int(delivery.get("media_sent") or 0)
        rem = int(prev.get("free_pulls_remaining") or 0)
        step = int(prev.get("free_pull_number") or 0)
        limit = int(prev.get("free_pull_limit") or 5)
        finale_markup = _loot_inline_keyboard(
            cfg,
            free_pull_number=step,
            free_pulls_remaining=rem,
            free_pull_limit=limit,
        )
        if media_sent <= 0:
            notes = ", ".join(str(x) for x in (delivery.get("notes") or []) if "skip" in str(x).lower())
            from app.services.loot_user_errors import loot_delivery_failed_user_html

            await _safe_reply_html(
                msg,
                loot_delivery_failed_user_html(
                    headline="Pull failed — no card delivered.",
                    technical_note=notes[:350] or "media load failed",
                ),
                disable_web_page_preview=True,
                reply_markup=finale_markup,
            )
            return
        step_label = f"Lesson {step}/5 · " if step else ""
        await _safe_reply_html(
            msg,
            f"<b>{step_label}Card dealt.</b>\n"
            "Read the lesson above, then <b>tap the blur</b> to unwrap.\n"
            f"<i>{rem} complimentary pull(s) left.</i>",
            disable_web_page_preview=True,
            reply_markup=finale_markup,
        )
        return

    if result.get("exhausted"):
        detail = result.get("detail") or {}
        body = detail.get("detail") if isinstance(detail, dict) else detail
        if isinstance(body, dict):
            from app.services.loot_free_tutorial import exhausted_hook_html

            pay = _payment_bot_username()
            hook = exhausted_hook_html(payment_bot_username=pay)
            ref_line = ""
            ref = await _fetch_referral_status(int(user.id))
            if ref and ref.get("loot_referrals_enabled") and ref.get("referral_link"):
                ref_line = (
                    f'\n\nRefer friends: <a href="{html.escape(str(ref["referral_link"]), quote=True)}">'
                    f'+{ref.get("referral_bonus_per_friend") or 1} pull each</a> (/referral)'
                )
            await _safe_reply_html(
                msg,
                hook + ref_line + "\n\n<i>Tap 📖 Guide for the full summary.</i>",
                disable_web_page_preview=True,
                reply_markup=_loot_inline_keyboard(context.application.bot_data.get("effective") or {}),
            )
        else:
            await _safe_reply_html(
                msg,
                "<b>No free pulls left.</b> Paid room — /loot on the payment bot.",
                reply_markup=_loot_inline_keyboard(context.application.bot_data.get("effective") or {}),
            )
        return

    reason = html.escape(str(result.get("reason") or result.get("detail") or "unknown"))
    await _safe_reply_html(
        msg,
        f"<b>Pull failed.</b>\n<code>{reason[:300]}</code>",
        disable_web_page_preview=True,
    )


def _claim_goblin_drop(telegram_user_id: int, token: str) -> dict:
    """POST /goblin/claim — cap-limited goblin grant via deep link."""
    url = f"{API_BASE}/goblin/claim"
    body = {"token": token.strip(), "telegram_user_id": int(telegram_user_id)}
    headers: dict[str, str] = {"Content-Type": "application/json"}
    key = (os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()
    if key:
        headers["X-TBCC-Internal-Key"] = key
    try:
        with httpx.Client(timeout=_LOOT_CLAIM_TIMEOUT) as client:
            r = client.post(url, json=body, headers=headers)
        if r.status_code == 409:
            return {"ok": False, "already_claimed": True, "detail": r.json()}
        if r.status_code == 410:
            return {"ok": False, "exhausted": True, "detail": r.json()}
        if r.status_code == 404:
            return {"ok": False, "not_found": True, "detail": r.json()}
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.exception("goblin claim failed")
        return {"ok": False, "reason": str(e)}


async def _handle_goblin_claim(msg, context: ContextTypes.DEFAULT_TYPE, user_id: int, token: str) -> None:
    cfg = context.application.bot_data.get("effective") or {}
    status_msg = await _safe_reply_html(msg, "<b>Goblin claim…</b>", disable_web_page_preview=True)
    try:
        result = await asyncio.to_thread(_claim_goblin_drop, int(user_id), token)
    except Exception:
        await _drop_transient_msg(status_msg)
        await _safe_reply_html(
            msg,
            "<b>Goblin claim failed</b>\nAPI unreachable — is TBCC backend running?",
            disable_web_page_preview=True,
            reply_markup=_loot_inline_keyboard(cfg),
        )
        return

    await _drop_transient_msg(status_msg)
    if result.get("ok"):
        delivery = result.get("delivery") or {}
        media_sent = int(delivery.get("media_sent") or 0)
        finale_markup = _loot_inline_keyboard(cfg)
        if media_sent <= 0:
            await _safe_reply_html(
                msg,
                "<b>Goblin grant missed delivery.</b> Try again if slots remain.",
                disable_web_page_preview=True,
                reply_markup=finale_markup,
            )
            return
        await _safe_reply_html(
            msg,
            "<b>👺 Goblin loot claimed!</b>\n"
            "<i>Complimentary pull — does not use your /roll allowance.</i>",
            disable_web_page_preview=True,
            reply_markup=finale_markup,
        )
        return

    if result.get("already_claimed"):
        await _safe_reply_html(
            msg,
            "<b>Already claimed</b> this goblin drop.",
            disable_web_page_preview=True,
            reply_markup=_loot_inline_keyboard(cfg),
        )
        return
    if result.get("exhausted"):
        await _safe_reply_html(
            msg,
            "<b>Goblin exhausted</b> — cap reached before you tapped.",
            disable_web_page_preview=True,
            reply_markup=_loot_inline_keyboard(cfg),
        )
        return
    if result.get("not_found"):
        await _safe_reply_html(
            msg,
            "<b>Invalid goblin link.</b>",
            disable_web_page_preview=True,
            reply_markup=_loot_inline_keyboard(cfg),
        )
        return

    detail = result.get("detail") or result.get("reason") or "unknown"
    await _safe_reply_html(
        msg,
        f"<b>Goblin claim failed.</b>\n<code>{html.escape(str(detail)[:300])}</code>",
        disable_web_page_preview=True,
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data.get("effective") or {}
    raw_arg = (context.args[0] if context.args else "").strip()
    arg = raw_arg.lower()

    user = update.effective_user
    msg = update.effective_message
    if not msg:
        return

    if user and raw_arg:
        try:
            from app.services.traffic_attribution import record_traffic_touch_from_bot

            record_traffic_touch_from_bot(int(user.id), raw_arg)
        except Exception:
            pass

    if arg == "loot_free":
        if await _redirect_loot_to_dm(update, context, start="loot_free"):
            return
        await cmd_roll(update, context)
        return

    if user and arg.startswith("goblin_"):
        # Token is case-sensitive (secrets.token_urlsafe); do not lower() the payload.
        token = raw_arg[len("goblin_") :].strip()
        if token:
            if await _redirect_loot_to_dm(update, context, start=raw_arg):
                return
            await _handle_goblin_claim(msg, context, int(user.id), token)
            return

    if user and arg.startswith("lootref_"):
        code = raw_arg[len("lootref_") :].strip()
        if code:
            ok = await _record_loot_referral(int(user.id), code)
            if ok:
                await _safe_reply_html(
                    msg,
                    "<b>Referral linked.</b> Your first roll credits whoever invited you.",
                    disable_web_page_preview=True,
                )

    if arg in ("loot_keys", "loot"):
        await _send_loot_keys_hint(msg, context)
        return

    if arg == "model":
        await _begin_creator_promo_dm(update, context)
        return

    if arg.startswith("src_lv_") and await _handle_lane_gate(msg, context, arg):
        return

    from app.services.bot_network_discovery import parse_network_start_payload, send_network_menu

    if parse_network_start_payload(arg):
        await send_network_menu(chat_id=msg.chat_id, context=context)
        return

    await _send_welcome(msg, context, cfg)


async def _handle_lane_gate(msg, context: ContextTypes.DEFAULT_TYPE, payload: str) -> bool:
    """Hand over the lane invite the user gated for, then cross-sell the room."""
    try:
        from app.services.lane_gate_relay import (
            lane_display_name,
            lane_invite_url,
            parse_lane_gate_payload,
        )

        parsed = parse_lane_gate_payload(payload)
    except Exception:
        logger.debug("lane gate parse failed for %s", payload, exc_info=True)
        return False
    if not parsed:
        return False

    lane, _week = parsed
    invite = lane_invite_url(lane)
    if not invite:
        return False

    name = lane_display_name(lane)
    cfg = context.application.bot_data.get("effective") or {}
    await _safe_reply_html(
        msg,
        f"<b>{html.escape(name)}</b> — you're in.\n\n"
        f'<a href="{html.escape(invite, quote=True)}">Open {html.escape(name)}</a>\n\n'
        "<i>Free pull while you're here: /roll · tap 🌐 Network for more lanes.</i>",
        disable_web_page_preview=False,
        reply_markup=_loot_inline_keyboard(cfg),
    )
    return True


async def _send_loot_keys_hint(msg, context: ContextTypes.DEFAULT_TYPE) -> None:
    pay = _payment_bot_username()
    cfg = context.application.bot_data.get("effective") or {}
    if pay:
        await _safe_reply_html(
            msg,
            "<b>24h room access</b>\n\n"
            f'Keys and checkout: <a href="https://t.me/{html.escape(pay)}?start=loot">@{html.escape(pay)}</a> → /loot',
            disable_web_page_preview=False,
            reply_markup=_loot_inline_keyboard(cfg),
        )
    else:
        await _safe_reply_html(
            msg,
            "<b>24h room access</b>\n\n"
            "Set <code>TBCC_PAYMENT_BOT_USERNAME</code> in tbcc/.env for checkout links.",
            disable_web_page_preview=False,
        )


async def cmd_guide(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.services.loot_free_tutorial import build_guide_summary_html

    msg = update.effective_message
    if not msg:
        return
    cfg = context.application.bot_data.get("effective") or {}
    await _safe_reply_html(
        msg,
        build_guide_summary_html(),
        disable_web_page_preview=True,
        reply_markup=_loot_inline_keyboard(cfg),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_welcome(update.effective_message, context) if update.effective_message else None


async def cmd_network(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    from app.services.bot_network_discovery import send_network_menu

    await send_network_menu(chat_id=msg.chat_id, context=context)


async def on_loot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("loot:"):
        return
    action = query.data.split(":", 1)[1]
    if action in ("roll", "referral", "loot_keys", "guide", "help") and await _redirect_loot_to_dm(update, context):
        return
    await query.answer()
    msg = query.message
    if not msg:
        return

    if action == "roll":
        await cmd_roll(update, context)
    elif action == "referral":
        await cmd_referral(update, context)
    elif action == "model":
        await cmd_model(update, context)
    elif action == "loot_keys":
        await _send_loot_keys_hint(msg, context)
    elif action == "help":
        await _send_welcome(msg, context)
    elif action == "guide":
        await cmd_guide(update, context)
    elif action == "creator_learn":
        await _send_creator_learn(msg, context)
    elif action == "creator_skip_name":
        await _creator_promo_submit_from_draft(update, context)
    elif action == "creator_cancel":
        _clear_creator_promo_state(context)
        await _safe_reply_html(msg, "<b>Creator promo cancelled.</b>", disable_web_page_preview=True)


def _loot_bot_username(cfg: dict | None = None) -> str:
    cfg = cfg or {}
    return (
        (cfg.get("bot_username") or os.getenv("TBCC_LOOT_BOT_USERNAME") or "aof_lootgod_bot")
        .strip()
        .lstrip("@")
    )


def _is_private_chat(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type == ChatType.PRIVATE)


async def _redirect_loot_to_dm(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    start: str = "loot_free",
) -> bool:
    from app.services.loot_dm_guard import (
        loot_dm_redirect_html,
        loot_dm_redirect_markup,
        should_redirect_loot_to_dm,
    )

    chat = update.effective_chat
    if not should_redirect_loot_to_dm(chat_type=str(chat.type) if chat else None):
        return False
    user = update.effective_user
    msg = update.effective_message
    if update.callback_query and not msg:
        msg = update.callback_query.message
    if not user or not msg:
        return True
    cfg = context.application.bot_data.get("effective") or {}
    bot_un = _loot_bot_username(cfg)
    if update.callback_query:
        try:
            await update.callback_query.answer("Open Loot God in DM")
        except TelegramError:
            pass
    await _safe_reply_html(
        msg,
        loot_dm_redirect_html(bot_username=bot_un),
        disable_web_page_preview=True,
        reply_markup=loot_dm_redirect_markup(bot_username=bot_un, start=start),
    )
    try:
        await context.bot.send_message(
            chat_id=int(user.id),
            text=(
                "<b>Loot Overseer</b>\n\n"
                "Rolls and albums deliver here in DM — not in group topics.\n"
                "Tap <b>Roll now</b> or send /roll."
            ),
            parse_mode="HTML",
            reply_markup=_loot_inline_keyboard(cfg),
        )
        await context.bot.send_message(
            chat_id=int(user.id),
            text="Quick actions:",
            reply_markup=_loot_reply_keyboard(),
        )
    except Forbidden:
        pass
    return True


def _clear_creator_promo_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("creator_promo_step", None)
    context.user_data.pop("creator_promo_draft", None)
    context.user_data.pop("awaiting_of_url", None)


def _creator_promo_dm_keyboard(cfg: dict) -> InlineKeyboardMarkup:
    bot_un = html.escape(_loot_bot_username(cfg))
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("📦 Open Creator promo in DM", url=f"https://t.me/{bot_un}?start=model")]]
    )


async def _redirect_creator_promo_to_dm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    cfg = context.application.bot_data.get("effective") or {}
    bot_un = _loot_bot_username(cfg)
    text = (
        "<b>Creator promo</b> submissions happen in DM — not in the group/channel feed.\n\n"
        f'Tap below to open <a href="https://t.me/{html.escape(bot_un)}?start=model">@{html.escape(bot_un)}</a> '
        "and paste your profile link there."
    )
    kb = _creator_promo_dm_keyboard(cfg)
    await _safe_reply_html(msg, text, disable_web_page_preview=True, reply_markup=kb)
    try:
        await context.bot.send_message(
            chat_id=int(user.id),
            text=(
                "<b>Creator promo</b>\n\n"
                "Paste your public profile URL in this chat — "
                "OnlyFans, Fansly, Fanvue, Linktree, Telegram, Snapchat, Kik, SextingFinder, and more.\n\n"
                "<i>Send the link in your next message.</i>"
            ),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        context.user_data["creator_promo_step"] = "await_url"
    except Forbidden:
        pass


async def _begin_creator_promo_dm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_private_chat(update):
        await _redirect_creator_promo_to_dm(update, context)
        return
    msg = update.effective_message
    if not msg:
        return
    _clear_creator_promo_state(context)
    context.user_data["creator_promo_step"] = "await_url"
    learn_kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("ℹ️ Learn more", callback_data="loot:creator_learn")],
            [InlineKeyboardButton("✖ Cancel", callback_data="loot:creator_cancel")],
        ]
    )
    from app.services.loot_creator_platforms import SUPPORTED_PLATFORM_LABELS

    await _safe_reply_html(
        msg,
        "<b>Creator promo application</b>\n\n"
        "Paste your <b>public creator profile URL</b>. After you submit, an operator reviews it "
        "before it goes live in the tier 5+ modifier pool.\n\n"
        f"<b>Supported:</b> {html.escape(SUPPORTED_PLATFORM_LABELS)}\n\n"
        "<i>Send one profile link per message. Gate/shortener links are rejected.</i>",
        disable_web_page_preview=True,
        reply_markup=learn_kb,
    )


async def _creator_promo_confirm_step(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    draft: dict,
) -> None:
    msg = update.effective_message
    if not msg:
        return
    context.user_data["creator_promo_step"] = "await_display_name"
    context.user_data["creator_promo_draft"] = draft
    label = html.escape(str(draft.get("label") or "Creator promo"))
    url = html.escape(str(draft.get("normalized_url") or ""))
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Submit for review", callback_data="loot:creator_skip_name")],
            [InlineKeyboardButton("✖ Cancel", callback_data="loot:creator_cancel")],
        ]
    )
    await _safe_reply_html(
        msg,
        f"<b>Link recognized</b>\n{label}\n<code>{url}</code>\n\n"
        "Optional: reply with a short <b>display name</b> for the caption label "
        "(or tap <b>Submit for review</b> to use the handle).",
        disable_web_page_preview=True,
        reply_markup=kb,
    )


async def _creator_promo_submit_from_draft(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    display_name: str | None = None,
) -> None:
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    draft = context.user_data.get("creator_promo_draft") or {}
    url = str(draft.get("submitted_url") or draft.get("normalized_url") or "").strip()
    if not url:
        _clear_creator_promo_state(context)
        await _safe_reply_html(msg, "<b>Nothing to submit.</b> Send /model to start again.", disable_web_page_preview=True)
        return
    try:
        result = await _submit_creator_url(int(user.id), url, display_name=display_name)
    except Exception:
        logger.exception("creator submit failed")
        await _safe_reply_html(msg, "<b>Submit failed</b> — API unreachable.", disable_web_page_preview=True)
        return
    _clear_creator_promo_state(context)
    if not result.get("ok"):
        detail = result.get("detail")
        err = detail if isinstance(detail, str) else str(detail)
        await _safe_reply_html(
            msg,
            f"<b>Could not accept link</b>\n{html.escape(err[:400])}",
            disable_web_page_preview=True,
        )
        return
    label = html.escape(str(result.get("label") or "Creator promo"))
    if result.get("already_registered"):
        note = html.escape(str(result.get("message") or ""))
        await _safe_reply_html(
            msg,
            f"<b>Already on file.</b> {label}\n<i>{note}</i>",
            disable_web_page_preview=True,
        )
        return
    sid = result.get("submission_id")
    sid_line = f"\n<i>Reference #{html.escape(str(sid))}</i>" if sid else ""
    await _safe_reply_html(
        msg,
        f"<b>✅ Submitted for review.</b> {label}{sid_line}\n\n"
        f"<i>{html.escape(str(result.get('message') or ''))}</i>",
        disable_web_page_preview=True,
    )


async def _handle_creator_url_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    raw_text: str,
) -> None:
    from app.services.loot_creator_platforms import label_from_creator_url, normalize_creator_url, unsupported_url_message

    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    parsed = normalize_creator_url(raw_text)
    if not parsed:
        await _safe_reply_html(
            msg,
            f"<b>Could not accept link</b>\n{unsupported_url_message()}",
            disable_web_page_preview=True,
        )
        return
    normalized, _platform_key, prefix, path_handle = parsed
    draft = {
        "submitted_url": raw_text.strip(),
        "normalized_url": normalized,
        "label": label_from_creator_url(prefix, path_handle),
    }
    await _creator_promo_confirm_step(update, context, draft)


async def _send_creator_learn(msg, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data.get("effective") or {}
    from app.services.loot_creator_platforms import SUPPORTED_PLATFORM_LABELS

    await _safe_reply_html(
        msg,
        "<b>Creator promo — how it works</b>\n\n"
        "Loot rolls can attach up to <b>3 bonus modifiers</b> (links or packs) after the main album. "
        "Your profile link enters that weighted pool on <b>tier 5+</b> paid rolls — "
        "players who hit a high tier may see your link hyperlinked under <b>Bonus unlocks</b>.\n\n"
        "<b>Supported platforms</b>\n"
        f"{html.escape(SUPPORTED_PLATFORM_LABELS)}\n\n"
        "<b>How to submit</b>\n"
        "Tap <b>Creator promo</b> or send <code>/model</code> in DM. "
        "In groups/channels the bot opens DM for you — submissions never spam the feed.\n\n"
        "<b>Review gate</b>\n"
        "Every link is reviewed before it goes live (blocks spam, gates, and malicious URLs).\n\n"
        "<b>Limits</b>\n"
        "• Same URL cannot be registered twice\n"
        "• Max 3 new applications per 24h\n"
        "• Max 5 pending + active promos per account\n\n"
        "<i>Tip: paste your main landing page — one clean profile URL rolls cleaner than redirects.</i>",
        disable_web_page_preview=True,
        reply_markup=_loot_inline_keyboard(cfg),
    )


async def cmd_referral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    ref = await _fetch_referral_status(int(user.id))
    if not ref:
        await _safe_reply_html(
            msg,
            "<b>Referral unavailable</b> — API down. Try again shortly.",
            disable_web_page_preview=True,
        )
        return
    if not ref.get("loot_referrals_enabled"):
        await _safe_reply_html(
            msg,
            "<b>Referrals are off</b> for this rollout.",
            disable_web_page_preview=True,
        )
        return
    link = str(ref.get("referral_link") or "")
    bonus = int(ref.get("referral_bonus_per_friend") or 1)
    rem = int(ref.get("free_pulls_remaining") or 0)
    total = int(ref.get("total_allowance") or 5)
    cfg = context.application.bot_data.get("effective") or {}
    await _safe_reply_html(
        msg,
        "<b>Loot referrals</b>\n\n"
        f"Share your link — when a friend uses their first complimentary /roll, you get "
        f"<b>+{bonus}</b> extra pull(s).\n\n"
        f'<a href="{html.escape(link, quote=True)}">{html.escape(link)}</a>\n\n'
        f"<i>You have {rem} of {total} complimentary pull(s) left.</i>",
        disable_web_page_preview=True,
        reply_markup=_loot_inline_keyboard(cfg),
    )


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    if not _is_private_chat(update):
        await _redirect_creator_promo_to_dm(update, context)
        return
    if context.args:
        await _handle_creator_url_input(update, context, " ".join(context.args).strip())
        return
    await _begin_creator_promo_dm(update, context)


async def on_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg or not msg.text:
        return
    text = msg.text.strip()

    shortcut = _LOOT_KEYBOARD.get(text)
    if shortcut == "roll":
        if await _redirect_loot_to_dm(update, context):
            return
        await cmd_roll(update, context)
        return
    if shortcut == "referral":
        await cmd_referral(update, context)
        return
    if shortcut == "loot_keys":
        await _send_loot_keys_hint(msg, context)
        return
    if shortcut == "model":
        await cmd_model(update, context)
        return
    if shortcut == "guide":
        await cmd_guide(update, context)
        return
    if text == "💬 Ask the Overseer":
        await _safe_reply_html(
            msg,
            "Ask anything about the Loot Room — tiers, pulls, or keys. Or tap <b>Roll now</b> above.",
            disable_web_page_preview=True,
        )
        return

    if context.user_data.get("creator_promo_step") == "await_url":
        await _handle_creator_url_input(update, context, text)
        return
    if context.user_data.get("creator_promo_step") == "await_display_name":
        await _creator_promo_submit_from_draft(update, context, display_name=text)
        return
    if context.user_data.get("awaiting_of_url"):
        await _handle_creator_url_input(update, context, text)
        return

    cfg = context.application.bot_data.get("effective") or {}
    from app.services.loot_narrative import narrative_enabled, reply_as_overseer
    from app.services.llm_chat import provider_configured

    if not narrative_enabled(cfg):
        return
    if not provider_configured():
        await _safe_reply_html(
            msg,
            "<b>Overseer voice offline.</b> Set <code>TBCC_OPENAI_API_KEY</code> (or Ollama) in tbcc/.env.",
            disable_web_page_preview=True,
        )
        return

    hist: list[dict[str, str]] = context.user_data.setdefault("narrative_history", [])
    hist.append({"role": "user", "content": text})
    hist = hist[-12:]
    context.user_data["narrative_history"] = hist
    try:
        reply = await reply_as_overseer(hist, effective=cfg)
    except Exception as e:
        logger.exception("overseer narrative failed")
        await _safe_reply_html(
            msg,
            f"<b>Overseer static.</b> <code>{html.escape(str(e)[:200])}</code>",
            disable_web_page_preview=True,
        )
        return
    hist.append({"role": "assistant", "content": reply})
    context.user_data["narrative_history"] = hist[-12:]
    await _safe_reply_html(msg, html.escape(reply), disable_web_page_preview=True)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data.get("effective") or {}
    lines = [
        "<b>Loot overseer status</b>",
        f"API: <code>{html.escape(API_BASE)}</code>",
        f"User-facing token: <code>{html.escape(str(cfg.get('bot_token_masked') or 'n/a'))}</code>",
        f"Token source: <code>{html.escape(str(cfg.get('bot_token_source') or '?'))}</code>",
        f"Narrative LLM layer: <code>{'on' if cfg.get('narrative_enabled') else 'off'}</code>",
        f"Loot referrals: <code>{'on' if cfg.get('loot_referral_enabled') else 'off'}</code>",
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
    commands = [
        BotCommand("start", "Welcome + action menu"),
        BotCommand("roll", "Claim a complimentary pull"),
        BotCommand("find", "Search archive by keyword or emoji"),
        BotCommand("referral", "Your referral link"),
        BotCommand("model", "Submit creator promo (DM review queue)"),
        BotCommand("help", "Show menu and shortcuts"),
        BotCommand("guide", "Full Loot Room guide (5-lesson summary)"),
    ]
    try:
        await application.bot.set_my_commands(commands)
        await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    except TelegramError as e:
        logger.warning("set_my_commands / menu: %s", e)


def _brief_update(update: object) -> str:
    if not isinstance(update, Update):
        return "update=?"
    if update.callback_query and update.callback_query.data:
        return f"callback={update.callback_query.data!r}"
    msg = update.effective_message
    if msg and msg.text:
        text = msg.text.strip()
        return f"text={text[:80]!r}" if len(text) > 80 else f"text={text!r}"
    if update.effective_user:
        return f"user_id={update.effective_user.id}"
    return "update=?"


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, Conflict):
        logger.error(
            "Telegram 409 Conflict — another loot_bot instance is polling the same token. "
            "Stop duplicate TBCC-LootBot processes and restart one."
        )
        return
    if isinstance(err, Forbidden):
        logger.info("Telegram Forbidden (blocked chat): %s", err)
        return
    if isinstance(err, NetworkError):
        logger.warning("Telegram network error: %s", err)
        return
    brief = _brief_update(update)
    if err is not None:
        detail = f"{type(err).__name__}: {err}"
        if err.__traceback__:
            tb = "".join(traceback.format_exception(type(err), err, err.__traceback__)).strip()
            logger.warning("Unhandled loot bot error (%s): %s\n%s", brief, detail, tb)
        else:
            logger.warning("Unhandled loot bot error (%s): %s", brief, detail)
        report_bot_error("TBCC-LootBot", f"unhandled ({brief})", err)
    else:
        logger.warning("Unhandled loot bot error (%s): unknown", brief)
        report_bot_error("TBCC-LootBot", f"unhandled ({brief})", "unknown")


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
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("guide", cmd_guide))
    application.add_handler(CommandHandler("roll", cmd_roll))
    application.add_handler(CommandHandler("daily", cmd_daily))
    application.add_handler(CommandHandler("viproll", cmd_viproll))
    from bots.aof_search_telegram import build_find_handlers

    for h in build_find_handlers(bot_kind="loot"):
        application.add_handler(h)
    application.add_handler(CommandHandler("referral", cmd_referral))
    application.add_handler(CommandHandler("model", cmd_model))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("network", cmd_network))
    application.add_handler(CallbackQueryHandler(on_loot_callback, pattern=r"^loot:"))
    from app.services.bot_network_discovery import on_network_callback

    application.add_handler(CallbackQueryHandler(on_network_callback, pattern=r"^aof_net:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_message))
    try:
        from bots.leave_message_cleanup import register_leave_cleanup_handler

        register_leave_cleanup_handler(application, bot_label="loot-bot")
    except Exception as e:
        logger.warning("leave-message cleanup not registered: %s", e)
    application.add_error_handler(on_error)
    logger.info(
        "Loot overseer starting (API %s), Telegram timeout=%.1fs, bootstrap_retries=%s%s",
        API_BASE,
        t,
        br,
        f", proxy={proxy}" if proxy else "",
    )
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        bootstrap_retries=br,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
