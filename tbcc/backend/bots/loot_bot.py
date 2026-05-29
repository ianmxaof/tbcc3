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
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

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


async def _submit_creator_url(telegram_user_id: int, url: str) -> dict:
    r = await asyncio.to_thread(
        _api_post_sync,
        "/loot/creator-submit",
        json_body={"url": url.strip(), "telegram_user_id": int(telegram_user_id)},
    )
    if r.status_code >= 400:
        detail = r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else r.text
        return {"ok": False, "detail": detail}
    data = r.json()
    data["ok"] = True
    return data


async def _claim_free_pull(telegram_user_id: int) -> dict:
    """POST /loot/free-pull/claim — delivers pull to user DM."""
    url = f"{API_BASE}/loot/free-pull/claim"
    params = {"telegram_user_id": int(telegram_user_id)}
    headers: dict[str, str] = {}
    key = (os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()
    if key:
        headers["X-TBCC-Internal-Key"] = key
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        r = client.post(url, params=params, headers=headers)
    if r.status_code == 403:
        return {"ok": False, "exhausted": True, "detail": r.json()}
    r.raise_for_status()
    return r.json()


async def cmd_roll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    msg = update.effective_message
    try:
        result = await asyncio.to_thread(_claim_free_pull, int(user.id))
    except httpx.HTTPStatusError as e:
        await msg.reply_html(
            f"<b>Pull failed</b>\n<code>{html.escape(str(e))}</code>",
            disable_web_page_preview=True,
        )
        return
    except Exception as e:
        logger.exception("free pull claim failed")
        await msg.reply_html(
            "<b>Pull failed</b>\nAPI unreachable — is TBCC backend running?",
            disable_web_page_preview=True,
        )
        return

    if result.get("ok"):
        prev = result.get("preview") or {}
        rem = int(prev.get("free_pulls_remaining") or 0)
        await msg.reply_html(
            f"<b>Pull dealt.</b> Tier {prev.get('rarity_tier') or '?'}. "
            f"<i>{rem} complimentary pull(s) left on this account.</i>",
            disable_web_page_preview=True,
        )
        return

    if result.get("exhausted"):
        detail = result.get("detail") or {}
        body = detail.get("detail") if isinstance(detail, dict) else detail
        if isinstance(body, dict):
            pay = (body.get("payment_link") or "").strip()
            pay_line = f'\n<a href="{html.escape(pay, quote=True)}">24h room access</a>' if pay else "\nPayment bot → /loot"
            ref_line = ""
            ref = await _fetch_referral_status(int(user.id))
            if ref and ref.get("loot_referrals_enabled") and ref.get("referral_link"):
                ref_line = (
                    f'\n\nRefer friends: <a href="{html.escape(str(ref["referral_link"]), quote=True)}">'
                    f'+{ref.get("referral_bonus_per_friend") or 1} pull each</a> (/referral)'
                )
            await msg.reply_html(
                "<b>No free pulls left.</b>\n"
                "Your complimentary allowance is spent.\n"
                "Paid runs attach megas, zips, group invites, and multi-slot modifiers."
                f"{pay_line}{ref_line}",
                disable_web_page_preview=True,
            )
        else:
            await msg.reply_html("<b>No free pulls left.</b> Paid room — /loot on the payment bot.")
        return

    await msg.reply_html("<b>Pull failed.</b>", disable_web_page_preview=True)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data.get("effective") or {}
    invite = cfg.get("primary_loot_room_invite_url") or "https://t.me/+97f4Crv3G1RkMGU5"
    un = cfg.get("bot_username") or "aof_lootgod_bot"
    spoiler = cfg.get("drop_spoiler_default", True)
    arg = (context.args[0] if context.args else "").strip().lower()

    user = update.effective_user
    if arg == "loot_free":
        await cmd_roll(update, context)
        return

    if user and arg.startswith("lootref_"):
        code = arg[8:].strip()
        if code:
            ok = await _record_loot_referral(int(user.id), code)
            if ok:
                await update.effective_message.reply_html(
                    "<b>Referral linked.</b> Your first /roll credits whoever invited you.",
                    disable_web_page_preview=True,
                )

    if arg in ("loot_keys", "loot"):
        pay_un = (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "").strip().lstrip("@")
        if pay_un:
            await update.effective_message.reply_html(
                "<b>24h room access</b>\n\n"
                f'Keys and checkout: <a href="https://t.me/{html.escape(pay_un)}?start=loot">@{html.escape(pay_un)}</a> → /loot',
                disable_web_page_preview=False,
            )
        else:
            await update.effective_message.reply_html(
                "<b>24h room access</b>\n\n"
                "Set <code>TBCC_PAYMENT_BOT_USERNAME</code> in tbcc/.env for checkout links.",
                disable_web_page_preview=False,
            )
        return

    lines = [
        "<b>Loot Overseer</b>",
        "",
        "Pulls run here. The private room is where the clock runs.",
        f'<a href="{html.escape(str(invite), quote=True)}">Loot Room</a>',
        "",
        "• Up to <b>5</b> complimentary pulls (/roll); <b>/referral</b> for bonus pulls after that\n"
        "• Models: <b>/model</b> — submit OnlyFans for loot modifier promos\n"
        "• 24h room access — payment bot /loot (timed drops, full table)\n",
    ]
    await update.effective_message.reply_html("\n".join(lines), disable_web_page_preview=False)


async def cmd_referral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    ref = await _fetch_referral_status(int(user.id))
    if not ref:
        await update.effective_message.reply_html(
            "<b>Referral unavailable</b> — API down. Try again shortly.",
            disable_web_page_preview=True,
        )
        return
    if not ref.get("loot_referrals_enabled"):
        await update.effective_message.reply_html(
            "<b>Referrals are off</b> for this rollout.",
            disable_web_page_preview=True,
        )
        return
    link = str(ref.get("referral_link") or "")
    bonus = int(ref.get("referral_bonus_per_friend") or 1)
    rem = int(ref.get("free_pulls_remaining") or 0)
    total = int(ref.get("total_allowance") or 5)
    await update.effective_message.reply_html(
        "<b>Loot referrals</b>\n\n"
        f"Share your link — when a friend uses their first complimentary /roll, you get "
        f"<b>+{bonus}</b> extra pull(s).\n\n"
        f'<a href="{html.escape(link, quote=True)}">{html.escape(link)}</a>\n\n'
        f"<i>You have {rem} of {total} complimentary pull(s) left.</i>",
        disable_web_page_preview=True,
    )


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    if context.args:
        url = " ".join(context.args).strip()
        await _handle_creator_url(update, context, url)
        return
    context.user_data["awaiting_of_url"] = True
    await update.effective_message.reply_html(
        "<b>Creator promo</b>\n\n"
        "Send your <b>OnlyFans profile URL</b> (https://onlyfans.com/yourhandle).\n"
        "It goes live in the loot modifier pool on tier 5+ rolls immediately.",
        disable_web_page_preview=True,
    )


async def _handle_creator_url(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str) -> None:
    user = update.effective_user
    if not user:
        return
    context.user_data.pop("awaiting_of_url", None)
    msg = update.effective_message
    try:
        result = await _submit_creator_url(int(user.id), url)
    except Exception:
        logger.exception("creator submit failed")
        await msg.reply_html("<b>Submit failed</b> — API unreachable.", disable_web_page_preview=True)
        return
    if not result.get("ok"):
        detail = result.get("detail")
        err = detail if isinstance(detail, str) else str(detail)
        await msg.reply_html(
            f"<b>Invalid profile link</b>\n{html.escape(err[:400])}",
            disable_web_page_preview=True,
        )
        return
    label = html.escape(str(result.get("label") or "Creator promo"))
    await msg.reply_html(
        f"<b>In the pool.</b> {label}\n<i>{html.escape(str(result.get('message') or ''))}</i>",
        disable_web_page_preview=True,
    )


async def on_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg or not msg.text:
        return
    text = msg.text.strip()

    if context.user_data.get("awaiting_of_url"):
        await _handle_creator_url(update, context, text)
        return

    cfg = context.application.bot_data.get("effective") or {}
    from app.services.loot_narrative import narrative_enabled, reply_as_overseer
    from app.services.llm_chat import provider_configured

    if not narrative_enabled(cfg):
        return
    if not provider_configured():
        await msg.reply_html(
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
        await msg.reply_html(
            f"<b>Overseer static.</b> <code>{html.escape(str(e)[:200])}</code>",
            disable_web_page_preview=True,
        )
        return
    hist.append({"role": "assistant", "content": reply})
    context.user_data["narrative_history"] = hist[-12:]
    await msg.reply_html(html.escape(reply), disable_web_page_preview=True)


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
    application.add_handler(CommandHandler("roll", cmd_roll))
    application.add_handler(CommandHandler("referral", cmd_referral))
    application.add_handler(CommandHandler("model", cmd_model))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_message))
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
