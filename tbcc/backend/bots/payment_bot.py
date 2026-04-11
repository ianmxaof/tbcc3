"""
Payment bot for subscriptions + digital packs.

Checkout: Telegram Stars (XTR) in-bot today; crypto & card (fiat) copy and plumbing are aligned
with the roadmap — same catalog, additional processors TBD.

Pipeline: catalog → send_invoice (XTR) → pre_checkout validation → successful_payment
→ POST /subscriptions (idempotent via telegram_payment_charge_id).

Run: python -m bots.payment_bot (from tbcc/backend with PYTHONPATH=backend)

Requires: BOT_TOKEN in tbcc/.env; TBCC_API_URL if API is not http://localhost:8000

Optional env (slow VPN / strict firewall / corporate proxy):
  TELEGRAM_HTTP_TIMEOUT — seconds for connect/read/write/pool (default 30; was PTB default 5).
  TELEGRAM_BOOTSTRAP_RETRIES — retries during startup if Telegram is slow (default 5; 0 = fail fast).
  TELEGRAM_PROXY — proxy URL for Bot API (or set HTTPS_PROXY / HTTP_PROXY; see httpx docs).
If you still see ConnectTimeout, confirm outbound HTTPS to api.telegram.org is allowed (firewall/VPN/DNS).
"""
import html
import io
import logging
import os
import random
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

# Allow `from app.utils...` when running `python -m bots.payment_bot` from tbcc/backend
_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from dotenv import load_dotenv

# Load tbcc/.env before importing shop_promo (needs TBCC_API_URL for /shop catalog)
_env = Path(__file__).resolve().parent.parent.parent / ".env"
if _env.exists():
    # Override shell/OS env so tbcc/.env is authoritative (fixes empty TBCC_INTERNAL_API_KEY
    # in the parent process blocking the key from .env, which causes 403 on /external-payment-orders/).
    load_dotenv(_env, override=True)

import httpx
from bots.growth_config_client import referral_cfg
from bots.payment_pipeline import validate_pre_checkout
from app.services.bundle_storage import bundle_zip2_path, bundle_zip_nth_path, bundle_zip_path
from app.services.llm_shop_suggest import hashtag_line_from_slugs
from app.utils.promo_url_normalize import normalize_promo_image_url
from app.utils.telegram_promo_url import is_public_https_for_telegram
from bots.shop_promo import send_shop_promo
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    InputMediaPhoto,
    LabeledPrice,
    Update,
)
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

API_BASE = os.getenv("TBCC_API_URL", "http://localhost:8000")


def _telegram_http_timeout_seconds() -> float:
    """PTB defaults to 5s connect — too short on some networks; clamp to a sane range."""
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


def _coerce_promo_fetch_url(raw: str) -> str:
    """
    Promo URLs saved as http://127.0.0.1:8000/static/promo/... fail when the bot runs in Docker
    or another host. Prefer TBCC_API_URL's host for HTTP downloads from this process.
    """
    try:
        u = urlparse(raw)
        if u.scheme not in ("http", "https") or not u.path:
            return raw
        if u.hostname not in ("127.0.0.1", "localhost"):
            return raw
        api = urlparse(API_BASE.rstrip("/") + "/")
        if not api.scheme or not api.netloc:
            return raw
        return urlunparse((api.scheme, api.netloc, u.path, "", u.query or "", u.fragment or ""))
    except Exception:
        return raw


def _pick_display_description(plan: dict) -> str:
    """Random line from primary description + description_variations (dashboard)."""
    base = str(plan.get("description") or "").strip()
    extras: list[str] = []
    raw = plan.get("description_variations")
    if isinstance(raw, list):
        for x in raw:
            s = str(x or "").strip()
            if s:
                extras.append(s)
    pool: list[str] = []
    if base:
        pool.append(base)
    for x in extras:
        if x not in pool:
            pool.append(x)
    if not pool:
        return ""
    return random.choice(pool)


def _plan_promo_urls(p: dict) -> list[str]:
    """Up to 5 HTTPS promo URLs for album + invoice (invoice uses first only)."""
    raw = p.get("promo_image_urls")
    if isinstance(raw, list):
        out: list[str] = []
        for x in raw:
            u = normalize_promo_image_url(str(x or ""))
            if u:
                out.append(u)
            if len(out) >= 5:
                break
        return out
    single = str(p.get("promo_image_url") or "").strip()
    if single:
        u = normalize_promo_image_url(single)
        return [u] if u else []
    return []


async def _maybe_send_promo_album_before_invoice(msg, plan: dict) -> bool:
    """
    If a product has 2+ promo URLs, send a Telegram media group first.
    Returns True when an album was sent — caller should omit invoice photo_url to avoid duplicating the first image.
    """
    urls = _plan_promo_urls(plan)[:10]
    if len(urls) <= 1:
        return False
    resolved: list[InputFile | str] = []
    for u in urls:
        ph = await _resolve_bundle_promo_photo(u)
        if ph is not None:
            resolved.append(ph)
    if len(resolved) <= 1:
        return False
    name = html.escape(str(plan.get("name") or "Product"))
    stars = int(plan.get("price_stars") or 0)
    cap = f"<b>{name}</b>\n{stars} ⭐"
    media: list[InputMediaPhoto] = []
    for i, ph in enumerate(resolved):
        if i == 0:
            media.append(InputMediaPhoto(media=ph, caption=cap, parse_mode="HTML"))
        else:
            media.append(InputMediaPhoto(media=ph))
    try:
        await msg.reply_media_group(media=media)
        return True
    except Exception as e:
        logger.warning("promo album before invoice failed plan_id=%s: %s", plan.get("id"), e)
        return False


async def _resolve_bundle_promo_photo(promo: str) -> InputFile | str | None:
    """
    Telegram's servers fetch photo URLs themselves — they cannot reach localhost/private URLs.

    If the dashboard stored http://127.0.0.1:8000/static/promo/... (default when no public base is set),
    we download the image here (same machine as the API) and send it as an uploaded file.
    Public https:// URLs are passed through as a string for Telegram to fetch.
    """
    raw = normalize_promo_image_url(promo)
    if not raw:
        return None
    if raw.startswith("/"):
        raw = f"{API_BASE.rstrip('/')}{raw}"
    if not raw.startswith(("http://", "https://")):
        return None
    if is_public_https_for_telegram(raw):
        return raw
    fetch_url = _coerce_promo_fetch_url(raw)
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(fetch_url, timeout=30.0, follow_redirects=True)
            r.raise_for_status()
            data = r.content
            if len(data) < 32:
                return None
            ext = ".jpg"
            if data[:8] == b"\x89PNG\r\n\x1a\n":
                ext = ".png"
            elif len(data) >= 6 and data[:6] in (b"GIF87a", b"GIF89a"):
                ext = ".gif"
            elif len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                ext = ".webp"
            return InputFile(io.BytesIO(data), filename=f"promo{ext}")
    except Exception as e:
        logger.warning("bundle promo download failed (%s): %s", fetch_url[:96], e)
        return None


def _plan_ok_for_stars_checkout(p: dict) -> bool:
    """Active subscription products with Stars price — matches dashboard shop filters."""
    if not isinstance(p, dict):
        return False
    if p.get("price_stars", 0) <= 0:
        return False
    if p.get("is_active") is False:
        return False
    ptype = (p.get("product_type") or "subscription").lower()
    if ptype != "subscription":
        return False
    return True


def _bundle_ok_for_stars_checkout(p: dict) -> bool:
    """Active digital pack / bundle products (product_type=bundle) with Stars price."""
    if not isinstance(p, dict):
        return False
    if p.get("price_stars", 0) <= 0:
        return False
    if p.get("is_active") is False:
        return False
    ptype = (p.get("product_type") or "subscription").lower()
    return ptype == "bundle"


async def _fetch_plans_raw() -> list[dict]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{API_BASE}/subscription-plans/")
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("Failed to fetch plans: %s", e)
        return []


async def fetch_plans() -> list[dict]:
    """Subscription products (group / channel access)."""
    return [p for p in await _fetch_plans_raw() if _plan_ok_for_stars_checkout(p)]


async def fetch_bundles() -> list[dict]:
    """Digital pack products (images/videos); configure in dashboard as product type *bundle*."""
    return [p for p in await _fetch_plans_raw() if _bundle_ok_for_stars_checkout(p)]


async def fetch_plan_by_id(plan_id: int) -> dict | None:
    """Resolve one product by id (subscription or bundle)."""
    for p in await _fetch_plans_raw():
        if p.get("id") == plan_id and p.get("is_active") is not False and (p.get("price_stars") or 0) > 0:
            return p
    return None


async def fetch_user_subscriptions(telegram_user_id: int) -> list[dict]:
    """Fetch user's subscriptions from backend."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{API_BASE}/subscriptions/",
                params={"telegram_user_id": telegram_user_id},
            )
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("Failed to fetch subscriptions: %s", e)
        return []


async def record_referral(referred_user_id: int, referrer_user_id: int) -> bool:
    """Record that user was referred (when they click ref link)."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{API_BASE}/referrals/",
                json={
                    "referred_user_id": referred_user_id,
                    "referrer_user_id": referrer_user_id,
                },
            )
            r.raise_for_status()
            return True
    except Exception as e:
        logger.warning("Failed to record referral: %s", e)
        return False


async def api_ensure_referral_code(telegram_user_id: int) -> dict | None:
    """Assign or return persistent short referral code (POST /referrals/ensure-code)."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{API_BASE}/referrals/ensure-code",
                json={"telegram_user_id": telegram_user_id},
                timeout=20.0,
            )
            r.raise_for_status()
            data = r.json()
            if data.get("error"):
                return None
            return data
    except Exception as e:
        logger.warning("ensure-code failed: %s", e)
        return None


async def lookup_referrer_by_code(code: str) -> int | None:
    """Resolve ref_<code> to Telegram user id (GET /referrals/by-code/{code})."""
    normalized = (code or "").strip().upper()
    if not normalized:
        return None
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{API_BASE}/referrals/by-code/{normalized}", timeout=15.0)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data = r.json()
            uid = data.get("telegram_user_id")
            return int(uid) if uid is not None else None
    except Exception as e:
        logger.warning("lookup referral code failed: %s", e)
        return None


def _fastapi_error_detail(r: httpx.Response) -> str | None:
    try:
        data = r.json()
        d = data.get("detail")
        if isinstance(d, str):
            return d
        if isinstance(d, list) and d:
            first = d[0]
            if isinstance(first, dict):
                return str(first.get("msg") or first.get("type") or first)
            return str(first)
    except Exception:
        pass
    return None


async def api_create_external_order(telegram_user_id: int, plan_id: int) -> tuple[dict | None, str | None]:
    """
    Create pending wallet/manual payment order (POST /external-payment-orders/).
    Returns (payload, None) on success, or (None, user_safe_error_hint) on failure.
    """
    headers = {}
    key = (os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()
    if key:
        headers["X-TBCC-Internal-Key"] = key
    url = f"{API_BASE.rstrip('/')}/external-payment-orders/"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                url,
                json={"telegram_user_id": telegram_user_id, "plan_id": plan_id},
                headers=headers,
                timeout=25.0,
            )
            if r.is_success:
                return r.json(), None
            body = (r.text or "")[:500]
            detail = _fastapi_error_detail(r)
            logger.warning(
                "external order create failed: %s %s — %s (TBCC_API_URL=%s key_set=%s)",
                r.status_code,
                r.reason_phrase,
                body,
                API_BASE,
                bool(key),
            )
            if r.status_code == 403:
                return None, (
                    "API rejected the request (missing or wrong X-TBCC-Internal-Key). "
                    "Set TBCC_INTERNAL_API_KEY in tbcc/.env to the same value the API uses, "
                    "then restart the payment bot and the API. "
                    "If the key is already in .env, restart the bot so it reloads the file."
                )
            if r.status_code == 404 and detail:
                return None, f"Product: {detail}"
            if detail:
                return None, detail
            return None, f"API error {r.status_code} from {API_BASE}"
    except httpx.ConnectError as e:
        logger.warning(
            "external order create failed (connect): %s (TBCC_API_URL=%s)",
            e,
            API_BASE,
        )
        return (
            None,
            f"Could not connect to the TBCC API at {API_BASE}. Start the backend (uvicorn) "
            "and ensure TBCC_API_URL matches where the API listens.",
        )
    except Exception as e:
        logger.warning(
            "external order create failed: %s (TBCC_API_URL=%s)",
            e,
            API_BASE,
        )
        return None, f"Request failed: {e!s}"


async def resolve_referrer_id_from_start_payload(payload: str) -> int | None:
    """Parse /start ref_* — short codes from referral_codes, or legacy numeric Telegram user ids."""
    if not payload.startswith("ref_"):
        return None
    rest = payload[4:]
    if not rest:
        return None
    # 8-char codes (letters + digits): always try DB first (avoids clashing with legacy ids)
    if len(rest) == 8:
        uid = await lookup_referrer_by_code(rest)
        if uid is not None:
            return uid
        if rest.isdigit():
            return int(rest)
        return None
    if not rest.isdigit():
        return await lookup_referrer_by_code(rest)
    return int(rest)


async def create_subscription(
    telegram_user_id: int,
    plan_id: int,
    payment_method: str = "stars",
    referrer_id: int | None = None,
    telegram_payment_charge_id: str | None = None,
) -> dict | None:
    """Create subscription / record purchase via backend API (idempotent on charge id)."""
    try:
        async with httpx.AsyncClient() as client:
            payload = {
                "telegram_user_id": telegram_user_id,
                "plan_id": plan_id,
                "payment_method": payment_method,
                "referral_reward_days": int(referral_cfg()["reward_days"]),
            }
            if referrer_id:
                payload["referrer_id"] = referrer_id
            if telegram_payment_charge_id:
                payload["telegram_payment_charge_id"] = telegram_payment_charge_id
            r = await client.post(f"{API_BASE}/subscriptions/", json=payload)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.exception("Failed to create subscription: %s", e)
        return None


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Quick actions (same as commands below)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💎 Premium (group)", callback_data="menu_subscribe"),
                InlineKeyboardButton("📦 Digital packs", callback_data="menu_packs"),
            ],
            [
                InlineKeyboardButton("🔗 Referral", callback_data="menu_referral"),
                InlineKeyboardButton("📋 Status", callback_data="menu_status"),
            ],
        ]
    )


def welcome_html() -> str:
    """Welcome + command list (HTML — Telegram Markdown is fragile with /commands, &, nested bold)."""
    pay_line = (
        "💳 <b>Payments:</b> <b>Telegram Stars</b> (in-app, live now) · <b>crypto</b> &amp; <b>card (fiat)</b> — "
        "same products; Stars checkout is active today, additional rails rolling out alongside.\n\n"
    )
    mode = referral_cfg()["mode"]
    if mode == "community":
        return (
            "👋 <b>Welcome!</b> Choose what you need:\n\n"
            + pay_line
            + "• /shop — Open the store (premium + packs)\n"
            "• /subscribe — Premium group access (Stars · crypto · card)\n"
            "• /packs — Digital packs (images / videos)\n"
            "• /referral — Your unique code + invite link &amp; rewards\n"
            "• /status — Your purchases &amp; subscription\n\n"
            "<i>Tap a button below or use the commands.</i>"
        )
    return (
        "👋 <b>Welcome!</b> Here’s what I offer:\n\n"
        + pay_line
        + "• /shop — Browse premium &amp; digital packs\n"
        "• /subscribe — Premium access to the group / channel (Stars · crypto · card)\n"
        "• /packs — One-time digital packs (images &amp; videos)\n"
        "• /referral — Your unique code + link; earn free days when friends subscribe\n"
        "• /status — See your active subscription &amp; purchases\n\n"
        "<i>Use the buttons or type a command.</i>"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help — same overview as /start (without referral deep-link side effects)."""
    msg = update.effective_message
    if not msg:
        return
    try:
        await msg.reply_text(
            welcome_html(),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    except BadRequest as e:
        logger.warning("cmd_help HTML failed: %s", e)
        await msg.reply_text(
            "Use /start for the menu. Commands: /shop /subscribe /packs /referral /status",
            reply_markup=main_menu_keyboard(),
        )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start - including ref_XXX deep link for referrals."""
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    # Parse deep link: /start ref_12345
    args = (context.args or [])
    payload = args[0] if args else ""

    if payload.startswith("ref_"):
        referrer_id = await resolve_referrer_id_from_start_payload(payload)
        if referrer_id is not None and referrer_id != user.id:
            await record_referral(user.id, referrer_id)
            rc = referral_cfg()
            mode = rc["mode"]
            group_link = rc["group_link"]
            group_name = rc["group_name"]
            if mode == "community" and group_link:
                await msg.reply_text(
                    f"👋 **Welcome!** You were invited by a friend.\n\n"
                    f"👇 Join {group_name}: {group_link}",
                    parse_mode="Markdown",
                )
            else:
                await msg.reply_text(
                    "👋 **Welcome!** You were invited by a friend.\n\n"
                    "Use /subscribe for premium access or /packs for digital packs.\n"
                    "_Pay with Stars in Telegram; crypto & card paths are rolling out._",
                    parse_mode="Markdown",
                )
            return

    try:
        await msg.reply_text(
            welcome_html(),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    except BadRequest as e:
        logger.warning("cmd_start welcome HTML failed: %s", e)
        await msg.reply_text(
            "Welcome! Use /shop, /subscribe, /packs, /referral, /status — or tap a button below.",
            reply_markup=main_menu_keyboard(),
        )


async def cmd_shop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Promotional /shop: hero + section images + FOMO copy + CTA (see shop_promo.py)."""
    msg = update.effective_message
    if not msg:
        return
    logger.info("/shop from user=%s chat=%s", update.effective_user.id if update.effective_user else None, msg.chat_id)
    await send_shop_promo(update, context)


async def reply_referral(msg, user, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send forward-ready message with user's unique referral code + link (persisted via API)."""
    if not msg or not user:
        return

    bot_info = await context.bot.get_me()
    bot_username = bot_info.username or "your_bot"

    ensured = await api_ensure_referral_code(user.id)
    ref_code: str | None = None
    start_param: str | None = None
    if ensured and ensured.get("code"):
        ref_code = str(ensured["code"])
        start_param = str(ensured.get("start_param") or f"ref_{ref_code}")
        ref_link = f"https://t.me/{bot_username}?start={start_param}"
    else:
        ref_link = f"https://t.me/{bot_username}?start=ref_{user.id}"

    rc = referral_cfg()
    group_link = rc["group_link"]
    reward_days = str(rc["reward_days"])
    group_name = rc["group_name"]
    mode = rc["mode"]
    is_community = mode == "community"

    # Forward-ready message: user taps Forward, sends anywhere
    if is_community:
        if group_link:
            forward_text = (
                f"🔥 Join {group_name}!\n\n"
                f"👇 {group_link}\n\n"
                f"Invited by me: {ref_link}\n\n"
                f"✨ Top referrers get early access when we launch premium!"
            )
        else:
            forward_text = (
                f"🔥 Join {group_name}!\n\n"
                f"{ref_link}\n\n"
                f"✨ Top referrers get early access when we launch premium!"
            )
        code_block = f"**Your code:** `{ref_code}`\n" if ref_code else ""
        confirm_text = (
            f"{code_block}"
            f"✅ **Your link:** `{ref_link}`\n\n"
            f"Share it! Top referrers get early access when premium launches."
        )
    else:
        if group_link:
            forward_text = (
                f"🔥 Join {group_name}!\n\n"
                f"👇 Free group: {group_link}\n\n"
                f"💎 Premium: {ref_link}\n\n"
                f"✨ Earn {reward_days} days free when friends subscribe via your link!"
            )
        else:
            forward_text = (
                f"🔥 Join {group_name}!\n\n"
                f"💎 Premium access: {ref_link}\n\n"
                f"✨ Earn {reward_days} days free when friends subscribe via your link!"
            )
        code_block = f"**Your code:** `{ref_code}`\n" if ref_code else ""
        confirm_text = (
            f"{code_block}"
            f"✅ **Your link:** `{ref_link}`\n"
            f"Earn **{reward_days} days free** per referral!"
        )

    await msg.reply_text("📤 **Tap Forward** on the message below to share:", parse_mode="Markdown")
    await context.bot.send_message(chat_id=msg.chat_id, text=forward_text)
    await msg.reply_text(confirm_text, parse_mode="Markdown")


async def cmd_referral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /referral."""
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    await reply_referral(msg, user, context)


def _truncate_btn(s: str, max_len: int = 64) -> str:
    """Telegram inline button text must be 1–64 chars; long plan names break keyboards."""
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


async def send_subscription_catalog_message(msg, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List subscription (group/channel) products — Stars invoice + separate wallet/manual message."""
    if not msg:
        return

    plans = await fetch_plans()
    if not plans:
        await msg.reply_text(
            "💎 **Premium access**\n\nNo subscription plans are listed yet. "
            "Ask the admin to add products in the dashboard (product type: subscription).",
            parse_mode="Markdown",
        )
        return

    # Two separate messages so wallet buttons are never hidden (Telegram max 64 chars per button label).
    stars_kb: list[list[InlineKeyboardButton]] = []
    wallet_kb: list[list[InlineKeyboardButton]] = []
    for p in plans:
        stars = p.get("price_stars", 0)
        name = p.get("name", "Plan")
        days = p.get("duration_days", 30)
        pid = int(p["id"])
        stars_kb.append(
            [
                InlineKeyboardButton(
                    _truncate_btn(f"{name} — {stars} ⭐ ({days}d)"),
                    callback_data=f"plan_{pid}",
                ),
            ]
        )
        wallet_kb.append(
            [
                InlineKeyboardButton(
                    _truncate_btn(f"Wallet / crypto — {name}", 64),
                    callback_data=f"ext_plan_{pid}",
                ),
            ]
        )

    await msg.reply_text(
        "💎 **Premium — Telegram Stars**\n\n"
        "Tap a plan — an **invoice** opens (Stars only).",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(stars_kb),
    )
    await msg.reply_text(
        "⛓ **Premium — wallet / crypto / Cash App**\n\n"
        "Same products as above. Tap to get an **order code (EPO-…)** and pay **outside** Telegram. "
        "An admin marks it paid and you get access.\n\n"
        "_This is a separate message so these buttons are always visible._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(wallet_kb),
    )


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /subscribe - show plan buttons (works in DM, groups, and channels)."""
    msg = update.effective_message
    if not msg:
        return
    await send_subscription_catalog_message(msg, context)


def _bundle_caption_html(p: dict) -> str:
    """Caption for pack card (Telegram limit 1024)."""
    name = str(p.get("name") or "Pack")
    stars = int(p.get("price_stars") or 0)
    desc = _pick_display_description(p)
    lines = [f"<b>{html.escape(name)}</b>", f"{stars} ⭐"]
    if desc:
        lines.append(html.escape(desc[:900]))
    tags = p.get("tags")
    slugs: list[str] = []
    if isinstance(tags, list):
        for t in tags:
            if isinstance(t, dict) and t.get("slug"):
                slugs.append(str(t["slug"]))
    ht = hashtag_line_from_slugs(slugs) if slugs else ""
    if ht:
        lines.append(html.escape(ht[:200]))
    cap = "\n".join(lines)
    if len(cap) > 1024:
        cap = cap[:1021] + "…"
    return cap


def _bundle_pick_keyboard(bundles: list[dict]) -> InlineKeyboardMarkup:
    """One button per pack name; two buttons per row. Telegram allows max ~100 buttons total."""
    row: list[InlineKeyboardButton] = []
    rows: list[list[InlineKeyboardButton]] = []
    for p in bundles[:100]:
        pid = int(p["id"])
        name = str(p.get("name") or f"Pack #{pid}")
        row.append(
            InlineKeyboardButton(
                _truncate_btn(name, 64),
                callback_data=f"pick_pack_{pid}",
            )
        )
        if len(row) >= 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


async def send_single_bundle_detail_messages(msg, context: ContextTypes.DEFAULT_TYPE, p: dict) -> None:
    """
    Send one pack: description + Stars Buy + separate wallet row (same as old per-pack catalog).
    """
    pid = p.get("id")
    stars = int(p.get("price_stars") or 0)
    promo_urls = _plan_promo_urls(p)[:10]
    cap = _bundle_caption_html(p)
    kb_stars = InlineKeyboardMarkup(
        [[InlineKeyboardButton(_truncate_btn(f"Buy — {stars} ⭐"), callback_data=f"pack_{pid}")]]
    )
    kb_wallet = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _truncate_btn(f"Wallet / crypto — pack #{pid}", 64),
                    callback_data=f"ext_pack_{pid}",
                )
            ]
        ]
    )
    try:
        resolved: list[InputFile | str] = []
        for u in promo_urls:
            ph = await _resolve_bundle_promo_photo(u)
            if ph is not None:
                resolved.append(ph)

        if not resolved and promo_urls:
            logger.warning(
                "bundle promo: plan_id=%s had %s promo URL(s) but none could be resolved "
                "(set TBCC_PROMO_PUBLIC_BASE_URL to https://… so Telegram can fetch, or run the bot where "
                "TBCC_API_URL can reach /static/promo/…)",
                pid,
                len(promo_urls),
            )

        if not resolved:
            await msg.reply_text(text=cap, parse_mode="HTML", reply_markup=kb_stars)
        elif len(resolved) == 1:
            photo = resolved[0]
            await msg.reply_photo(
                photo=photo, caption=cap, parse_mode="HTML", reply_markup=kb_stars
            )
        else:
            media: list[InputMediaPhoto] = []
            for i, ph in enumerate(resolved):
                if i == 0:
                    media.append(InputMediaPhoto(media=ph, caption=cap, parse_mode="HTML"))
                else:
                    media.append(InputMediaPhoto(media=ph))
            await msg.reply_media_group(media=media)
            await msg.reply_text(
                f"⬇️ <b>{html.escape(str(p.get('name') or 'Pack'))}</b> — Stars checkout",
                parse_mode="HTML",
                reply_markup=kb_stars,
            )
    except Exception as e:
        logger.warning("bundle detail send failed plan_id=%s: %s", pid, e)
        try:
            await msg.reply_text(text=cap, parse_mode="HTML", reply_markup=kb_stars)
        except Exception as e2:
            logger.warning("bundle detail fallback send failed: %s", e2)
    try:
        await msg.reply_text(
            "⛓ <b>Same pack — pay outside Telegram</b> (order code). Tap:",
            parse_mode="HTML",
            reply_markup=kb_wallet,
        )
    except Exception as e:
        logger.warning("bundle wallet keyboard send failed plan_id=%s: %s", pid, e)


async def send_bundle_catalog_message(msg, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Digital packs: one intro + button grid (pick a pack). Full description + payments only after tap.
    """
    if not msg:
        return

    bundles = await fetch_bundles()
    if not bundles:
        await msg.reply_text(
            "📦 **Digital packs**\n\n"
            "No **bundle** products yet — this list is **only** for product type **Bundle** (digital zip packs).\n\n"
            "**Premium subscriptions** (AOF tiers, etc.) appear under **/subscribe** or **Premium**, not here.\n\n"
            "In the **dashboard → Shop products**, create a **new** product and set type to **Bundle (digital pack)** "
            "with a **Stars price** set and **active** checked.",
            parse_mode="Markdown",
        )
        return

    extra = ""
    if len(bundles) > 100:
        extra = f"\n\n<i>Showing buttons for the first 100 of {len(bundles)} packs.</i>"
    await msg.reply_text(
        "📦 <b>Digital packs</b>\n\n"
        "Tap a pack below — you’ll get the <b>description</b>, then <b>Buy</b> (Stars) and "
        "<b>Wallet / crypto</b> (order code) for that pack only."
        + extra,
        parse_mode="HTML",
        reply_markup=_bundle_pick_keyboard(bundles),
    )


async def handle_pick_pack_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User chose a pack from the /packs button grid — send that pack’s detail + payment rows."""
    query = update.callback_query
    if not query or not query.data:
        return
    msg = query.message
    if not msg:
        await query.answer()
        return
    if not query.data.startswith("pick_pack_"):
        await query.answer()
        return
    rest = query.data.replace("pick_pack_", "", 1)
    if not rest.isdigit():
        await query.answer()
        return
    pid = int(rest)
    plan = await fetch_plan_by_id(pid)
    if not plan:
        await query.answer("Product not found.", show_alert=True)
        return
    ptype = (plan.get("product_type") or "").lower()
    if ptype != "bundle":
        await query.answer("Invalid product.", show_alert=True)
        return
    await query.answer()
    await send_single_bundle_detail_messages(msg, context, plan)


async def cmd_packs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /packs — digital image/video bundles."""
    msg = update.effective_message
    if not msg:
        return
    await send_bundle_catalog_message(msg, context)


async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline buttons from /start menu."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    msg = query.message
    user = query.from_user
    if not msg or not user:
        return
    if query.data == "menu_subscribe":
        await send_subscription_catalog_message(msg, context)
    elif query.data == "menu_packs":
        await send_bundle_catalog_message(msg, context)
    elif query.data == "menu_referral":
        await reply_referral(msg, user, context)
    elif query.data == "menu_status":
        await reply_status(msg, user, context)


async def handle_external_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Wallet / manual: create external order with reference code + instructions (admin marks paid in API)."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    user = query.from_user
    msg = query.message
    if not user or not msg:
        return

    data = query.data
    if data.startswith("ext_plan_"):
        pid = int(data.replace("ext_plan_", ""))
        want = "subscription"
    elif data.startswith("ext_pack_"):
        pid = int(data.replace("ext_pack_", ""))
        want = "bundle"
    else:
        return

    plan = await fetch_plan_by_id(pid)
    if not plan:
        await msg.reply_text("Product not found or inactive.")
        return
    ptype = (plan.get("product_type") or "subscription").lower()
    if want == "subscription" and ptype != "subscription":
        await msg.reply_text("Invalid product.")
        return
    if want == "bundle" and ptype != "bundle":
        await msg.reply_text("Invalid product.")
        return

    result, order_err = await api_create_external_order(user.id, pid)
    if not result:
        hint = order_err or (
            "Could not create a payment order. Ensure the TBCC API is running and "
            "tbcc/.env has TBCC_INTERNAL_API_KEY matching the API."
        )
        await msg.reply_text(f"Could not create a payment order.\n\n{hint}")
        return

    instr = result.get("instructions_html") or ""
    ref = (result.get("order") or {}).get("reference_code", "?")
    header = f"<b>Order</b> <code>{html.escape(str(ref))}</code>\n\n"
    pay_url = result.get("crypto_pay_url")
    pay_extra = ""
    if pay_url:
        eu = html.escape(str(pay_url), quote=True)
        pay_extra += (
            "\n\n🔗 <a href=\"" + eu + "\">Pay with crypto (automatic)</a>\n"
            "<i>Access unlocks when payment confirms — no admin step.</i>"
        )
    details = result.get("crypto_pay_details")
    if details:
        pay_extra += "\n\n" + str(details)
    try:
        await msg.reply_text(header + instr + pay_extra, parse_mode="HTML")
    except BadRequest as e:
        logger.warning("external order message failed: %s", e)
        await msg.reply_text(f"Order {ref} created. Check API logs if instructions did not show.")

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass


async def handle_product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send invoice when user picks subscription (plan_) or pack (pack_)."""
    query = update.callback_query
    await query.answer()

    if not query.data:
        return
    parts = query.data.split("_", 1)
    if len(parts) != 2:
        return
    kind, rest = parts[0], parts[1]
    if kind not in ("plan", "pack") or not rest.isdigit():
        return

    plan_id = int(rest)
    plan = await fetch_plan_by_id(plan_id)
    if not plan:
        await query.edit_message_text("Product not found or no longer available.")
        return

    ptype = (plan.get("product_type") or "subscription").lower()
    if kind == "plan" and ptype != "subscription":
        await query.edit_message_text("Product not found or no longer available.")
        return
    if kind == "pack" and ptype != "bundle":
        await query.edit_message_text("Product not found or no longer available.")
        return

    price_stars = plan.get("price_stars", 0)
    if price_stars <= 0:
        await query.edit_message_text("This product has no price set.")
        return

    desc = _pick_display_description(plan)
    if not desc:
        if ptype == "bundle":
            desc = "Digital pack — images & videos"
        else:
            desc = f"Subscription — {plan.get('duration_days', 30)} days access"

    invoice_payload = (
        f"sub_{plan_id}_{query.from_user.id}"
        if ptype == "subscription"
        else f"bundle_{plan_id}_{query.from_user.id}"
    )

    album_sent = False
    if query.message:
        album_sent = await _maybe_send_promo_album_before_invoice(query.message, plan)

    # Telegram fetches photo_url from its servers — localhost / http / private IPs never work.
    promo_urls = _plan_promo_urls(plan)
    promo = "" if album_sent else (promo_urls[0] if promo_urls else "")
    invoice_kw: dict = {
        "chat_id": query.message.chat_id,
        "title": plan.get("name", "Product")[:128],
        "description": desc[:255],
        "payload": invoice_payload,
        "provider_token": "",
        "currency": "XTR",
        "prices": [LabeledPrice(label=plan.get("name", "Product")[:64], amount=price_stars)],
    }
    if is_public_https_for_telegram(promo):
        invoice_kw["photo_url"] = promo
    elif promo:
        logger.info(
            "Skipping invoice photo_url (not public HTTPS for Telegram) plan_id=%s url=%s",
            plan_id,
            promo[:100],
        )

    try:
        await context.bot.send_invoice(**invoice_kw)
    except BadRequest as e:
        # Some hosts (or WEBP/GIF) are rejected; retry without photo so checkout still works.
        if invoice_kw.get("photo_url") and (
            "photo" in str(e).lower() or "wrong" in str(e).lower() or "invalid" in str(e).lower()
        ):
            logger.warning("send_invoice photo rejected, retrying without photo: %s", e)
            invoice_kw.pop("photo_url", None)
            await context.bot.send_invoice(**invoice_kw)
        else:
            raise

    # Photo messages cannot be edited to plain text — only strip the Buy button, then nudge user.
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception as e:
        logger.debug("edit_message_reply_markup after invoice: %s", e)
    try:
        await query.message.reply_text("⬇️ Complete payment in the invoice above.")
    except Exception:
        pass


async def reply_status(msg, user, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Status text shared by /status and menu."""
    if not msg:
        return
    if not user:
        await msg.reply_text("Use /status in a private chat with me to see your subscription status.")
        return

    subs = await fetch_user_subscriptions(user.id)
    active = [s for s in subs if s.get("status") == "active"]
    expired = [s for s in subs if s.get("status") == "expired"]

    if not subs:
        await msg.reply_text(
            "📋 **Your status**\n\n"
            "No purchases yet.\n"
            "Use **/subscribe** for group access or **/packs** for digital packs.",
            parse_mode="Markdown",
        )
        return

    lines = ["📋 **Your subscription status**\n"]
    if active:
        lines.append("✅ **Active:**")
        for s in active:
            plan = s.get("plan", "—")
            exp = s.get("expires_at", "—")
            if isinstance(exp, str) and len(exp) > 19:
                exp = exp[:19].replace("T", " ")
            lines.append(f"  • {plan} — expires {exp}")
    if expired:
        lines.append("\n⏳ **Expired:**")
        for s in expired[:3]:
            lines.append(f"  • {s.get('plan', '—')}")
        if len(expired) > 3:
            lines.append(f"  … and {len(expired) - 3} more")

    lines.append("\nUse /subscribe or /packs to buy again.")
    await msg.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status - show user's subscription state."""
    msg = update.effective_message
    user = update.effective_user
    if not msg:
        return
    await reply_status(msg, user, context)


async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Validate invoice (payload, user, XTR amount) before Telegram charges Stars."""
    query = update.pre_checkout_query
    if not query:
        return
    ok, err = await validate_pre_checkout(query, fetch_plan_by_id)
    if ok:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message=err or "Payment not available")


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle successful payment - create subscription and grant access."""
    payment = update.message.successful_payment
    charge_id = (getattr(payment, "telegram_payment_charge_id", None) or "").strip() or None
    payload = payment.invoice_payload or ""

    if not (payload.startswith("sub_") or payload.startswith("bundle_")):
        await update.message.reply_text("Payment received. Thank you!")
        return

    parts = payload.split("_")
    if len(parts) < 3:
        await update.message.reply_text("Payment received. Thank you!")
        return

    plan_id = int(parts[1])
    user_id = update.effective_user.id if update.effective_user else 0
    is_bundle = payload.startswith("bundle_")

    sub = await create_subscription(
        user_id,
        plan_id,
        "stars",
        telegram_payment_charge_id=charge_id,
    )
    if sub:
        replay = bool(sub.get("fulfillment_replay"))
        progress_line = f"\n\n{sub.get('milestone_progress', '')}" if sub.get("milestone_progress") else ""
        # Notify referrer of reward (subscription only; backend skips for bundles)
        referrer_id = sub.get("referrer_id")
        if referrer_id and not is_bundle and not replay:
            reward_days = str(referral_cfg()["reward_days"])
            try:
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=f"🎉 **Referral reward!** A friend subscribed via your link. You've earned **{reward_days} days free**!",
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.warning("Could not notify referrer %s: %s", referrer_id, e)

        if is_bundle or (sub.get("plan_product_type") or "").lower() == "bundle":
            desc = (sub.get("plan_description") or "").strip()
            link = sub.get("invite_link")
            if link:
                text = (
                    "✅ **Pack unlocked!**\n\n"
                    f"Join here for your content:\n👉 {link}\n\n"
                    + (f"{desc}\n" if desc else "")
                )
            elif desc:
                text = f"✅ **Pack unlocked!**\n\n{desc}"
            else:
                text = (
                    "✅ **Purchase complete!** Thank you.\n\n"
                    "Your download is attached below when a zip was uploaded in the dashboard."
                )
            await update.message.reply_text(text, parse_mode="Markdown")
            if sub.get("bundle_zip_available"):
                cap_single = "📦 Your digital pack (zip)"
                parts = sub.get("bundle_zip_parts")
                if isinstance(parts, list) and parts:
                    total = len(parts)
                    for i, fn in enumerate(parts):
                        if not isinstance(fn, str) or not fn.strip():
                            continue
                        zp = bundle_zip_nth_path(plan_id, i)
                        if not zp.is_file():
                            continue
                        disp = fn.strip()[:250]
                        cap = f"📦 Part {i + 1} of {total}" if total > 1 else cap_single
                        try:
                            await update.message.reply_document(
                                document=InputFile(zp),
                                filename=disp,
                                caption=cap,
                            )
                        except Exception as e:
                            logger.warning("Could not send bundle zip part %s: %s", i, e)
                else:
                    zp = bundle_zip_path(plan_id)
                    z2p = bundle_zip2_path(plan_id)
                    both_parts = (
                        zp.is_file()
                        and z2p.is_file()
                        and (sub.get("bundle_zip_original_name") or "").strip()
                        and (sub.get("bundle_zip2_original_name") or "").strip()
                    )
                    if zp.is_file() and (sub.get("bundle_zip_original_name") or "").strip():
                        fn = (sub.get("bundle_zip_original_name") or f"pack_{plan_id}.zip")[:250]
                        try:
                            await update.message.reply_document(
                                document=InputFile(zp),
                                filename=fn,
                                caption="📦 Your digital pack (part 1 of 2)" if both_parts else cap_single,
                            )
                        except Exception as e:
                            logger.warning("Could not send bundle zip: %s", e)
                    if z2p.is_file() and (sub.get("bundle_zip2_original_name") or "").strip():
                        fn2 = (sub.get("bundle_zip2_original_name") or f"pack_{plan_id}_2.zip")[:250]
                        try:
                            await update.message.reply_document(
                                document=InputFile(z2p),
                                filename=fn2,
                                caption="📦 Your digital pack (part 2 of 2)" if both_parts else cap_single,
                            )
                        except Exception as e:
                            logger.warning("Could not send bundle zip part 2: %s", e)
            return

        link = sub.get("invite_link")
        if link:
            text = (
                "✅ **Payment successful!**\n\n"
                "You have been granted access. Join the premium channel here:\n"
                f"👉 {link}\n\n"
                "If you were already added, you can use this link as a backup."
                f"{progress_line}"
            )
        else:
            text = (
                "✅ **Payment successful!**\n\n"
                "You have been granted access to the premium channel. "
                "Check your Telegram for an invite or access link."
                f"{progress_line}"
            )
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "Payment received, but there was an issue granting access. "
            "Please contact support with your payment details.",
        )


async def _post_init(app: Application) -> None:
    """Log bot identity; register command menu + short description (visible before user sends /start)."""
    me = await app.bot.get_me()
    logger.info("Payment bot online: @%s id=%s — /shop uses MessageHandler + promo flow", me.username, me.id)
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{API_BASE.rstrip('/')}/health", timeout=10.0)
            if r.is_success:
                data = r.json()
                impl = data.get("external_payment_orders_impl")
                if impl != "uuid-epo-v2":
                    impl2 = None
                    try:
                        r2 = await client.get(
                            f"{API_BASE.rstrip('/')}/external-payment-orders/_impl", timeout=10.0
                        )
                        if r2.is_success:
                            impl2 = (r2.json() or {}).get("impl")
                    except Exception:
                        pass
                    logger.error(
                        "TBCC API at %s is not running the current tbcc/backend code: "
                        "/health has external_payment_orders_impl=%r (need 'uuid-epo-v2'); "
                        "/external-payment-orders/_impl impl=%r. "
                        "Close every TBCC-Backend window, confirm nothing else uses port 8000, then start "
                        "Uvicorn only from this repo: cd tbcc\\backend && python -m uvicorn app.main:app "
                        "--host 127.0.0.1 --port 8000 --reload --reload-exclude scripts --reload-delay 1 "
                        "(or run ..\\run-backend.cmd from tbcc). Wallet/crypto uses old code until fixed.",
                        API_BASE,
                        impl,
                        impl2,
                    )
                else:
                    logger.info("TBCC API OK: external_payment_orders_impl=uuid-epo-v2")
            else:
                logger.warning("TBCC API /health HTTP %s — check TBCC_API_URL and that the API is running", r.status_code)
    except Exception as e:
        logger.warning("TBCC API /health check failed (%s): %s", API_BASE, e)
    # Telegram does not send an update when someone only *opens* the chat — users must tap Start or send /help.
    # set_my_commands + set_my_short_description makes commands visible in the menu and on the bot profile card.
    commands = [
        BotCommand("start", "Welcome & main menu"),
        BotCommand("help", "Commands & what this bot does"),
        BotCommand("shop", "Open the store"),
        BotCommand("subscribe", "Premium — Stars, crypto & fiat"),
        BotCommand("packs", "Digital packs"),
        BotCommand("referral", "Your code, link & rewards"),
        BotCommand("status", "Your subscription & purchases"),
    ]
    try:
        await app.bot.set_my_commands(commands)
    except Exception as e:
        logger.warning("set_my_commands failed: %s", e)
    try:
        await app.bot.set_my_short_description(
            "AOF — community & premium. Stars live; crypto & card rolling out. /start or /help."
        )
    except Exception as e:
        logger.warning("set_my_short_description failed: %s", e)
    # Long profile text (“What can this bot do?”) — max 512 chars for set_my_description
    long_desc = (
        "AOF — Join the community and get premium access.\n\n"
        "Use /start or /help for the full menu.\n\n"
        "• /shop — Store (premium + packs)\n"
        "• /subscribe — Premium (Telegram Stars in-app; crypto & card rolling out)\n"
        "• /packs — Digital packs\n"
        "• /referral — Your unique code + invite link & rewards\n"
        "• /status — Purchases & subscription\n\n"
        "Referral: share your link; top referrers get perks. Subscribe: Stars now; same products on crypto/fiat next."
    )
    if len(long_desc) > 512:
        long_desc = long_desc[:509] + "..."
    try:
        await app.bot.set_my_description(long_desc)
    except Exception as e:
        logger.warning("set_my_description failed: %s", e)


def main() -> None:
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        print("BOT_TOKEN not set. Create a bot via @BotFather and add BOT_TOKEN to tbcc/.env")
        return

    # Regex handlers: /help and /shop match /cmd@BotName reliably (same pattern as /shop).
    help_cmd = filters.TEXT & filters.Regex(r"(?i)^/help(@\w+)?(\s|$)")
    # /shop: regex handler matches /shop, /Shop, /shop@YourBot (more reliable than CommandHandler alone in some clients)
    shop_cmd = filters.TEXT & filters.Regex(r"(?i)^/shop(@\w+)?(\s|$)")
    shop_channel = filters.UpdateType.CHANNEL_POST & filters.TEXT & filters.Regex(r"(?i)^/shop(@\w+)?(\s|$)")

    t = _telegram_http_timeout_seconds()
    br = _telegram_bootstrap_retries()
    b = (
        Application.builder()
        .token(token)
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
    logger.info(
        "Telegram HTTP timeouts: %.1fs (set TELEGRAM_HTTP_TIMEOUT); bootstrap_retries=%s (TELEGRAM_BOOTSTRAP_RETRIES)",
        t,
        br,
    )
    app.add_handler(MessageHandler(help_cmd, cmd_help))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(shop_cmd, cmd_shop))
    app.add_handler(MessageHandler(shop_channel, cmd_shop))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("packs", cmd_packs))
    app.add_handler(CommandHandler("referral", cmd_referral))
    app.add_handler(CommandHandler("status", cmd_status))
    # Handle /subscribe in channels (CommandHandler only matches message, not channel_post)
    app.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST & filters.Regex(r"^/subscribe(@\w+)?\s*$"),
            cmd_subscribe,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST & filters.Regex(r"^/status(@\w+)?\s*$"),
            cmd_status,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST & filters.Regex(r"^/referral(@\w+)?\s*$"),
            cmd_referral,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST & filters.Regex(r"^/packs(@\w+)?\s*$"),
            cmd_packs,
        )
    )
    app.add_handler(
        CallbackQueryHandler(handle_menu_callback, pattern=r"^menu_(subscribe|packs|referral|status)$")
    )
    app.add_handler(CallbackQueryHandler(handle_pick_pack_callback, pattern=r"^pick_pack_\d+$"))
    app.add_handler(CallbackQueryHandler(handle_external_payment_callback, pattern=r"^ext_(plan|pack)_\d+$"))
    app.add_handler(CallbackQueryHandler(handle_product_callback, pattern=r"^(plan|pack)_\d+$"))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(
        MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment),
    )

    print("Payment bot running. Commands: /start, /help, /shop, /subscribe, /packs, /referral, /status")
    app.run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=br)


if __name__ == "__main__":
    main()
