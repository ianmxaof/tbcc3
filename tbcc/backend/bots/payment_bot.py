"""
Payment bot for subscriptions + digital packs.

Checkout: Telegram Stars (XTR) in-bot today; crypto & card (fiat) copy and plumbing are aligned
with the roadmap — same catalog, additional processors TBD.

Pipeline: catalog → send_invoice (XTR) → pre_checkout validation → successful_payment
→ POST /subscriptions (idempotent via telegram_payment_charge_id).

Run: python -m bots.payment_bot (from tbcc/backend with PYTHONPATH=backend)

Requires: BOT_TOKEN in tbcc/.env; TBCC_API_URL if API is not http://localhost:8000

Optional: /resolve needs TBCC_INTERNAL_API_KEY, TBCC_BYPASS_API_KEY on the API + worker, Redis, and Celery
consuming queues link + link_priority (see tbcc/.env.example).

Optional env (slow VPN / strict firewall / corporate proxy):
  TELEGRAM_HTTP_TIMEOUT — seconds for connect/read/write/pool (default 30; was PTB default 5).
  TELEGRAM_BOOTSTRAP_RETRIES — retries during startup if Telegram is slow (default 5; 0 = fail fast).
  TELEGRAM_PROXY — proxy URL for Bot API (or set HTTPS_PROXY / HTTP_PROXY; see httpx docs).
If you still see ConnectTimeout, confirm outbound HTTPS to api.telegram.org is allowed (firewall/VPN/DNS).

Optional env (catalog):
  TBCC_BOT_MIN_SUBSCRIPTION_STARS — minimum Stars price for subscription rows in the bot (0 = off). Use e.g. 101 to hide a 100 ⭐ test SKU.
  TBCC_SUBSCRIPTION_CATALOG_COLUMNS — subscription Stars/crypto keyboard: buttons per row, 1–4 (default 2).
"""
import asyncio
import html
import io
import logging
import os
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse, urlunparse

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
from app.services.telegram_stars_invoice import (
    plan_invoice_description,
    stars_invoice_payload,
)
from bots.shop_promo import send_shop_promo
from bots.macro_search_telegram import build_macro_search_handlers, cmd_macrosearch
from bots.error_reporter import make_error_handler
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
    ChatMemberHandler,
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

# Set from GET /health in _post_init — used in welcome copy.
_health_crypto_auto_checkout: bool = False
_runtime_settings_cache: dict | None = None
_runtime_settings_loaded_at: float = 0.0
_runtime_settings_ttl_s = 30.0

_default_main_menu = [
    [{"label": "🗝 Loot Room (24h key)", "action": "menu_loot"}],
    [
        {"label": "💎 Premium (group)", "action": "menu_subscribe"},
        {"label": "📦 Digital packs", "action": "menu_packs"},
    ],
    [
        {"label": "🔗 Referral", "action": "menu_referral"},
        {"label": "📋 Status", "action": "menu_status"},
    ],
]


def _nowpayments_currency_label(pay_currency_slug: str | None) -> str:
    """Short human label for dashboard button text and payment messages (uses env as fallback)."""
    s = (pay_currency_slug or os.getenv("TBCC_NOWPAYMENTS_PAY_CURRENCY") or "").strip().lower()
    if not s:
        return "Crypto"
    if s == "usdttrc20":
        return "USDT"
    if s in ("usdterc20", "usdt_erc20"):
        return "USDT (ERC-20)"
    if s == "btc":
        return "BTC"
    if s == "eth":
        return "ETH"
    if s == "ton":
        return "TON"
    if s.startswith("usdt"):
        return "USDT"
    if len(s) <= 10:
        return s.upper()
    return s[:10] + "…"


def _runtime_settings_defaults() -> dict:
    return {
        "main_menu": _default_main_menu,
        "welcome_html": "",
        "loot_intro_html": "",
        "subscribe_title_main": "💎 **Premium Access**",
        "subscribe_title_loot": "🗝 **Loot Room Access**",
        "subscription_catalog_columns": 2,
        "min_subscription_stars": _bot_min_subscription_stars(),
        "video_finder_enabled": True,
        "video_finder_sources": [
            {
                "id": "bestcamvideos",
                "name": "BestCamVideos",
                "url": "https://bestcamvideos.com/?s={username}",
            },
            {
                "id": "camwhores",
                "name": "CamWhores",
                "url": "https://www.camwhores.tv/search/{username}/",
            },
        ],
        "video_finder_max_links_per_source": 8,
    }


def _normalized_runtime_settings(raw: dict | None) -> dict:
    base = _runtime_settings_defaults()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for key in out.keys():
        if key in raw:
            out[key] = raw[key]
    try:
        cols = int(out.get("subscription_catalog_columns") or 2)
    except (TypeError, ValueError):
        cols = 2
    out["subscription_catalog_columns"] = max(1, min(4, cols))
    try:
        min_stars = int(out.get("min_subscription_stars") or 0)
    except (TypeError, ValueError):
        min_stars = 0
    out["min_subscription_stars"] = max(0, min_stars)
    if not isinstance(out.get("main_menu"), list) or not out["main_menu"]:
        out["main_menu"] = _default_main_menu
    out["video_finder_enabled"] = bool(out.get("video_finder_enabled", True))
    try:
        out["video_finder_max_links_per_source"] = max(
            1,
            min(30, int(out.get("video_finder_max_links_per_source") or 8)),
        )
    except (TypeError, ValueError):
        out["video_finder_max_links_per_source"] = 8
    raw_sources = out.get("video_finder_sources")
    clean_sources: list[dict[str, str]] = []
    if isinstance(raw_sources, list):
        for item in raw_sources[:60]:
            if not isinstance(item, dict):
                continue
            sid = str(item.get("id") or "").strip()
            name = str(item.get("name") or "").strip()
            url = str(item.get("url") or "").strip()
            if not sid or not name or "{username}" not in url:
                continue
            if not url.startswith(("http://", "https://")):
                continue
            clean_sources.append({"id": sid[:64], "name": name[:128], "url": url[:1024]})
    out["video_finder_sources"] = clean_sources or _runtime_settings_defaults()["video_finder_sources"]
    macro_sources = out.get("macro_search_sources")
    if not isinstance(macro_sources, list) or not macro_sources:
        try:
            from app.services.model_search_engine import get_macro_search_sites

            out["macro_search_sources"] = get_macro_search_sites()
        except Exception:
            out["macro_search_sources"] = []
    macro_custom = out.get("macro_search_custom_sources")
    if not isinstance(macro_custom, list):
        out["macro_search_custom_sources"] = []
    return out


async def _patch_macro_custom_sources(custom: list) -> bool:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.patch(
                f"{API_BASE.rstrip('/')}/payment-bot-settings",
                json={"macro_search_custom_sources": custom},
                timeout=15.0,
            )
            return r.is_success
    except Exception as e:
        logger.warning("patch macro_search_custom_sources failed: %s", e)
        return False


async def _force_refresh_runtime_settings() -> None:
    await _get_runtime_settings(force_refresh=True)


async def _get_runtime_settings(force_refresh: bool = False) -> dict:
    global _runtime_settings_cache, _runtime_settings_loaded_at
    now = time.monotonic()
    if (
        not force_refresh
        and _runtime_settings_cache is not None
        and (now - _runtime_settings_loaded_at) < _runtime_settings_ttl_s
    ):
        return _runtime_settings_cache
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{API_BASE.rstrip('/')}/payment-bot-settings", timeout=10.0)
            if r.is_success:
                payload = r.json()
                effective = payload.get("effective") if isinstance(payload, dict) else None
                _runtime_settings_cache = _normalized_runtime_settings(effective)
            else:
                _runtime_settings_cache = _runtime_settings_cache or _runtime_settings_defaults()
    except Exception:
        _runtime_settings_cache = _runtime_settings_cache or _runtime_settings_defaults()
    _runtime_settings_loaded_at = now
    return _runtime_settings_cache


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


def _bot_min_subscription_stars() -> int:
    """Optional floor so placeholder / test subscription SKUs stay out of the bot (see TBCC_BOT_MIN_SUBSCRIPTION_STARS)."""
    try:
        raw = (os.getenv("TBCC_BOT_MIN_SUBSCRIPTION_STARS") or "").strip()
        if not raw:
            return 0
        return max(0, int(raw))
    except ValueError:
        return 0


def _subscription_catalog_columns() -> int:
    """Inline keyboard width for /subscribe plan grid (default 2)."""
    try:
        n = int((os.getenv("TBCC_SUBSCRIPTION_CATALOG_COLUMNS") or "2").strip() or "2")
    except ValueError:
        n = 2
    return max(1, min(4, n))


def _plan_ok_for_stars_checkout(p: dict, min_stars: int | None = None) -> bool:
    """Active subscription products with Stars price — matches dashboard shop filters."""
    if not isinstance(p, dict):
        return False
    if p.get("price_stars", 0) <= 0:
        return False
    m = _bot_min_subscription_stars() if min_stars is None else max(0, int(min_stars))
    if m > 0 and int(p.get("price_stars") or 0) < m:
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
            r = await client.get(f"{API_BASE}/subscription-plans/", timeout=15.0)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list) and data:
                return data
    except Exception as e:
        logger.warning("Failed to fetch plans from API (%s): %s — using DB fallback", API_BASE, e)
    return await asyncio.to_thread(_fetch_plans_raw_db)


def _fetch_plans_raw_db() -> list[dict]:
    """Catalog fallback when TBCC API is down — same JSON shape as GET /subscription-plans/."""
    from app.database.session import SessionLocal
    from app.models.subscription_plan import SubscriptionPlan
    from app.api.subscription_plans import _attach_tags_to_plan_dicts, _plan_dict

    db = SessionLocal()
    try:
        rows = db.query(SubscriptionPlan).all()
        dicts = [_plan_dict(p) for p in rows]
        _attach_tags_to_plan_dicts(db, rows, dicts)
        return dicts
    finally:
        db.close()


def _fetch_plan_by_id_db(plan_id: int) -> dict | None:
    from app.database.session import SessionLocal
    from app.models.subscription_plan import SubscriptionPlan
    from app.api.subscription_plans import _attach_tags_to_plan_dicts, _plan_dict

    pid = int(plan_id)
    db = SessionLocal()
    try:
        row = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == pid).first()
        if not row:
            return None
        d = _plan_dict(row)
        _attach_tags_to_plan_dicts(db, [row], [d])
        return d if _plan_row_usable(d, plan_id=pid) else None
    finally:
        db.close()


def _plan_row_usable(p: dict | None, *, plan_id: int | None = None) -> bool:
    if not isinstance(p, dict) or p.get("error"):
        return False
    if plan_id is not None:
        try:
            if int(p.get("id")) != int(plan_id):
                return False
        except (TypeError, ValueError):
            return False
    if p.get("is_active") is False:
        return False
    return int(p.get("price_stars") or 0) > 0


async def fetch_plan_by_id(plan_id: int) -> dict | None:
    """Resolve one product by id (subscription or bundle)."""
    pid = int(plan_id)
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{API_BASE}/subscription-plans/{pid}", timeout=15.0)
            if r.status_code == 404:
                return await asyncio.to_thread(_fetch_plan_by_id_db, pid)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and data.get("error"):
                data = None
            if data and _plan_row_usable(data, plan_id=pid):
                return data
    except Exception as e:
        logger.warning("fetch_plan_by_id(%s) API failed (%s): %s — DB fallback", pid, API_BASE, e)

    found = await asyncio.to_thread(_fetch_plan_by_id_db, pid)
    if found:
        return found

    for p in await _fetch_plans_raw():
        try:
            if int(p.get("id")) == pid and _plan_row_usable(p):
                return p
        except (TypeError, ValueError):
            continue
    return None


def _plan_in_bot_section(p: dict, section: str) -> bool:
    sec = str(p.get("bot_section") or "main").strip().lower()
    want = (section or "main").strip().lower()
    if not want:
        want = "main"
    return sec == want


async def fetch_plans(section: str = "main", min_stars: int | None = None) -> list[dict]:
    """Subscription products (group/channel access), grouped by bot section."""
    out = [
        p
        for p in await _fetch_plans_raw()
        if _plan_ok_for_stars_checkout(p, min_stars=min_stars) and _plan_in_bot_section(p, section)
    ]
    out.sort(key=lambda p: (int(p.get("duration_days") or 0), int(p.get("id") or 0)))
    return out


async def fetch_bundles() -> list[dict]:
    """Digital pack products (images/videos); configure in dashboard as product type *bundle*."""
    return [p for p in await _fetch_plans_raw() if _bundle_ok_for_stars_checkout(p)]


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


async def api_link_resolver_create(telegram_user_id: int, url: str) -> tuple[dict | None, str | None]:
    """POST /link-resolver/requests — returns (request_dict, error_hint)."""
    headers = {}
    key = (os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()
    if key:
        headers["X-TBCC-Internal-Key"] = key
    api_url = f"{API_BASE.rstrip('/')}/link-resolver/requests"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                api_url,
                json={"telegram_user_id": telegram_user_id, "url": url},
                headers=headers,
                timeout=30.0,
            )
            if r.is_success:
                data = r.json()
                req = data.get("request") if isinstance(data, dict) else None
                if isinstance(req, dict):
                    return req, None
                return None, "Invalid API response"
            body = (r.text or "")[:500]
            detail = _fastapi_error_detail(r)
            if r.status_code == 403:
                return None, (
                    "API rejected the request (missing or wrong X-TBCC-Internal-Key). "
                    "Set TBCC_INTERNAL_API_KEY in tbcc/.env for the bot and API."
                )
            if r.status_code == 503:
                return None, detail or body or "Link resolver unavailable (Bypass API key or Celery?)."
            return None, detail or body or f"API error {r.status_code}"
    except httpx.ConnectError:
        return (
            None,
            f"Could not connect to TBCC API at {API_BASE}. Start the backend and set TBCC_API_URL.",
        )
    except Exception as e:
        logger.warning("link_resolver create failed: %s", e)
        return None, f"Request failed: {e!s}"


async def api_link_resolver_get(request_public_id: str, telegram_user_id: int) -> tuple[dict | None, str | None]:
    """GET /link-resolver/requests/{id}?telegram_user_id=…"""
    headers = {}
    key = (os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()
    if key:
        headers["X-TBCC-Internal-Key"] = key
    api_url = f"{API_BASE.rstrip('/')}/link-resolver/requests/{request_public_id}"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                api_url,
                params={"telegram_user_id": telegram_user_id},
                headers=headers,
                timeout=20.0,
            )
            if r.is_success:
                data = r.json()
                req = data.get("request") if isinstance(data, dict) else None
                if isinstance(req, dict):
                    return req, None
                return None, "Invalid API response"
            if r.status_code in (403, 404):
                return None, "Not found or access denied."
            return None, _fastapi_error_detail(r) or (r.text or "")[:300]
    except Exception as e:
        logger.warning("link_resolver get failed: %s", e)
        return None, str(e)[:300]


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


def main_menu_keyboard(settings: dict | None = None) -> InlineKeyboardMarkup:
    """Quick actions (dashboard-configurable tree)."""
    st = _normalized_runtime_settings(settings)
    rows: list[list[InlineKeyboardButton]] = []
    for row in st.get("main_menu") or _default_main_menu:
        out_row: list[InlineKeyboardButton] = []
        if not isinstance(row, list):
            continue
        for btn in row:
            if not isinstance(btn, dict):
                continue
            label = str(btn.get("label") or "").strip()
            action = str(btn.get("action") or "").strip()
            if not label or not action.startswith("menu_"):
                continue
            out_row.append(InlineKeyboardButton(label[:64], callback_data=action))
        if out_row:
            rows.append(out_row)
    if not rows:
        return main_menu_keyboard(_runtime_settings_defaults())
    return InlineKeyboardMarkup(rows)


def welcome_html(settings: dict | None = None) -> str:
    """Welcome + command list (HTML — Telegram Markdown is fragile with /commands, &, nested bold)."""
    st = _normalized_runtime_settings(settings)
    custom = str(st.get("welcome_html") or "").strip()
    if custom:
        return custom
    if _health_crypto_auto_checkout:
        pay_line = (
            "💳 <b>Payments:</b> <b>Telegram Stars</b> (in-app) + <b>Wallet / crypto</b> (auto checkout link when available).\n"
            "⚡ <i>Access unlocks automatically after confirmation.</i>\n\n"
        )
    else:
        pay_line = (
            "💳 <b>Payments:</b> <b>Telegram Stars</b> (in-app, live now) + <b>Wallet / crypto</b>.\n"
            "⚡ <i>Crypto may use auto checkout when NOWPayments + public HTTPS API are configured; otherwise use order code flow.</i>\n\n"
        )
    body = (
        "👋 <b>Welcome to AOF Access Bot</b>\n\n"
        + pay_line
        + "🔥 <b>Main actions</b>\n"
        "• /shop — Full storefront (premium + packs + featured offers)\n"
        "• /loot — Loot Room section (24-hour key + private group run)\n"
        "• /subscribe — Premium memberships\n"
        "• /packs — Digital packs\n"
        "• /resolve — Unwrap supported ad/short links (needs API bypass key + Celery worker)\n"
        "• /macrosearch — Macro model search (TBCC extension sources) + video URLs\n"
        "• /videofind — Same as /macrosearch\n\n"
        "📌 <b>Account</b>\n"
        "• /status — Purchases &amp; active access\n"
        "• /referral — Your invite link + rewards\n\n"
    )
    from app.services.aof_social_links import donation_link_html

    donate = donation_link_html(label="support AOF ☕")
    if donate:
        body += f"☕ <b>Tip jar:</b> {donate}\n\n"
    body += "<i>Tap a button below or run any command.</i>"
    return body


async def cmd_resolve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resolve ad/short links via TBCC link-resolver + Bypass.vip (async Celery job)."""
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    args = context.args or []
    if not args:
        await msg.reply_text(
            "Usage: /resolve <url>\n\n"
            "Unwraps supported ad-link intermediaries when the server has a Bypass API key configured "
            "and a Celery worker is running with queues **link** and **link_priority**.\n"
            "Active subscribers get the priority queue and higher hourly limits."
        )
        return
    url = " ".join(args).strip()
    try:
        max_wait = int(os.getenv("TBCC_LINK_RESOLVER_POLL_MAX_S", "120"))
    except ValueError:
        max_wait = 120
    max_wait = max(15, min(max_wait, 300))

    status_msg = await msg.reply_text("⏳ Resolving…")
    created, err = await api_link_resolver_create(user.id, url)
    if err or not created:
        await status_msg.edit_text(f"❌ Could not start resolve: {err or 'unknown error'}")
        return
    public_id = created.get("public_id")
    if not public_id:
        await status_msg.edit_text("❌ Invalid response from API (missing request id).")
        return

    terminal = frozenset(("succeeded", "failed", "blocked"))
    elapsed = 0
    last: dict | None = None
    while elapsed < max_wait:
        row, gerr = await api_link_resolver_get(str(public_id), user.id)
        if gerr or not row:
            await status_msg.edit_text(f"❌ Lost job status: {gerr or 'unknown'}")
            return
        last = row
        st = (row.get("status") or "").lower()
        if st in terminal:
            break
        elapsed += 1
        if elapsed % 10 == 0:
            try:
                await status_msg.edit_text(f"⏳ Still resolving… ({elapsed}s)")
            except BadRequest:
                pass
        await asyncio.sleep(1)

    if not last:
        await status_msg.edit_text("❌ Timeout waiting for resolver.")
        return
    st = (last.get("status") or "").lower()
    if st == "succeeded" and last.get("final_url"):
        risk = last.get("risk_level") or "low"
        out = last["final_url"]
        await status_msg.edit_text(
            f"✅ Resolved ({risk} risk)\n\n{out}",
            disable_web_page_preview=True,
        )
        return
    if st == "blocked":
        reason = last.get("reason_code") or "blocked"
        await status_msg.edit_text(f"🚫 Blocked: {reason}")
        return
    detail = last.get("error_detail") or last.get("reason_code") or "failed"
    await status_msg.edit_text(f"❌ Resolve failed: {detail}")


def _normalize_video_username(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("@"):
        s = s[1:]
    s = re.sub(r"^[^\w]+|[^\w.-]+$", "", s)
    if not re.fullmatch(r"[A-Za-z0-9._-]{2,64}", s or ""):
        return ""
    return s


def _build_video_search_url(template: str, username: str) -> str:
    return str(template or "").replace("{username}", quote(username, safe=""))


def _extract_urls_from_html(
    html_text: str,
    page_url: str,
    source_cfg: dict,
    username: str,
    max_links: int,
) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    pattern = str(source_cfg.get("result_link_regex") or "").strip()
    must_inc = [str(x).strip().lower() for x in (source_cfg.get("result_link_must_include") or []) if str(x).strip()]
    deny_inc = [str(x).strip().lower() for x in (source_cfg.get("result_link_deny_include") or []) if str(x).strip()]
    root_host = (urlparse(page_url).hostname or "").lower()

    raw_hits: list[str] = []
    if pattern:
        try:
            rx = re.compile(pattern, re.IGNORECASE)
            for m in rx.finditer(html_text):
                if m.groups():
                    raw_hits.append(m.group(1))
                else:
                    raw_hits.append(m.group(0))
        except re.error:
            raw_hits = []
    if not raw_hits:
        raw_hits = re.findall(r"""href\s*=\s*["']([^"'#]+)["']""", html_text, flags=re.IGNORECASE)

    for raw in raw_hits:
        if not raw:
            continue
        u = html.unescape(str(raw).strip())
        full = urljoin(page_url, u)
        if not full.startswith(("http://", "https://")):
            continue
        try:
            pu = urlparse(full)
        except Exception:
            continue
        host = (pu.hostname or "").lower()
        if root_host and host and host != root_host:
            continue
        lower = full.lower()
        if any(x in lower for x in ("javascript:", "mailto:", "/cdn-cgi/", ".css", ".js")):
            continue
        if any(d in lower for d in deny_inc):
            continue
        if must_inc and not any(m in lower for m in must_inc):
            continue
        if not must_inc:
            looks_like_video = any(k in lower for k in ("/video", "/videos", "/watch", "/clip", "/movie"))
            has_username = username.lower() in lower
            if not (looks_like_video or has_username):
                continue
        if full in seen:
            continue
        seen.add(full)
        links.append(full)
        if len(links) >= max_links:
            break
    return links


async def _fetch_source_video_links(
    source_cfg: dict,
    username: str,
    max_links: int,
) -> tuple[list[str], str | None]:
    search_url = _build_video_search_url(str(source_cfg.get("url") or ""), username)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            r = await client.get(search_url, headers=headers)
        if not r.is_success:
            return [], f"http_{r.status_code}"
        links = _extract_urls_from_html(r.text or "", str(r.url), source_cfg, username, max_links)
        if not links:
            return [], "no_matches"
        return links, None
    except Exception as e:
        logger.warning("videofind source fetch failed source=%s: %s", source_cfg.get("id"), e)
        return [], "fetch_failed"


async def cmd_videofind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Alias for /macrosearch — same macro engine + extension source list."""
    await cmd_macrosearch(update, context, get_settings=_get_runtime_settings)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help — same overview as /start (without referral deep-link side effects)."""
    msg = update.effective_message
    if not msg:
        return
    st = await _get_runtime_settings()
    try:
        await msg.reply_text(
            welcome_html(st),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(st),
        )
    except BadRequest as e:
        logger.warning("cmd_help HTML failed: %s", e)
        await msg.reply_text(
            "Use /start for the menu. Commands: /shop /loot /subscribe /packs /referral /status /resolve /macrosearch /videofind",
            reply_markup=main_menu_keyboard(),
        )


async def send_loot_room_message(msg, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dedicated Loot Room menu + plans from bot_section=loot."""
    if not msg:
        return
    st = await _get_runtime_settings()
    custom_loot_intro = str(st.get("loot_intro_html") or "").strip()
    intro = custom_loot_intro or (
        "<b>Loot Room — 24h access</b>\n\n"
        "One purchase. One window.\n"
        "Private room entry for 24 hours; @aof_lootgod_bot handles your pulls.\n\n"
        "<b>During the run</b>\n"
        "• Tiered drops (low to max)\n"
        "• Up to three modifier slots per pull\n"
        "• Spoiler delivery — you peel what you earned\n\n"
        "<b>Select a key</b>"
    )
    await msg.reply_text(
        intro,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Loot Room keys", callback_data="menu_loot_subscribe")],
                [InlineKeyboardButton("🛍 Open Full Store", callback_data="menu_shop")],
            ]
        ),
    )


async def cmd_loot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Loot Room offer section: 24h key + private group flow."""
    msg = update.effective_message
    await send_loot_room_message(msg, context)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    st = await _get_runtime_settings()
    """Handle /start - including ref_XXX deep link for referrals."""
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    # Parse deep link: /start ref_12345
    args = (context.args or [])
    payload = args[0] if args else ""

    if payload.startswith("vf_") or payload.startswith("ms_"):
        username = _normalize_video_username(payload[3:])
        if username:
            context.args = [username]
            await cmd_videofind(update, context)
            return

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

    # Dashboard scheduled post → Stars invoice (c6) or menu with crypto (cm6)
    m_menu = re.match(r"^cm(\d+)(?:_([A-Za-z0-9]{1,16}))?$", payload)
    m_checkout = re.match(r"^c(\d+)(?:_([A-Za-z0-9]{1,16}))?$", payload)
    if m_menu or m_checkout:
        plan_id = int((m_menu or m_checkout).group(1))
        ref_suffix = (m_menu or m_checkout).group(2)
        menu_mode = bool(m_menu)
        if ref_suffix:
            referrer_uid = await lookup_referrer_by_code(ref_suffix)
            if referrer_uid is not None and referrer_uid != user.id:
                await record_referral(user.id, referrer_uid)
        plan = await fetch_plan_by_id(plan_id)
        if not plan:
            await msg.reply_text("That offer is not available anymore.")
            return
        ptype = (plan.get("product_type") or "subscription").lower()
        if ptype not in ("subscription", "bundle"):
            await msg.reply_text("That product is not available for quick checkout.")
            return
        if menu_mode:
            await send_simple_plan_checkout(
                msg,
                context,
                [plan],
                pack=(ptype == "bundle"),
            )
        else:
            await _send_stars_invoice(
                context,
                msg,
                user.id,
                plan,
            )
        return

    try:
        await msg.reply_text(
            welcome_html(st),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(st),
        )
    except BadRequest as e:
        logger.warning("cmd_start welcome HTML failed: %s", e)
        await msg.reply_text(
            "Welcome! Use /shop, /loot, /subscribe, /packs, /referral, /status — or tap a button below.",
            reply_markup=main_menu_keyboard(st),
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


def _subscription_duration_badge(duration_days) -> str:
    """Short human label for plan length (avoid 36500d-style noise in button text)."""
    try:
        d = int(duration_days)
    except (TypeError, ValueError):
        d = 30
    if d <= 0:
        return "—"
    if d >= 20000:
        return "long"
    if d >= 3600:
        return f"{d // 365}y+"
    if d >= 300:
        return f"{d // 365}y"
    if d >= 120:
        m = max(1, round(d / 30))
        return f"{m}mo"
    if d == 1:
        return "1d"
    return f"{d}d"


def _inline_buttons_in_rows(buttons: list[InlineKeyboardButton], columns: int) -> list[list[InlineKeyboardButton]]:
    if columns < 1:
        columns = 1
    if columns > 4:
        columns = 4
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(buttons), columns):
        rows.append(buttons[i : i + columns])
    return rows


def _subscription_stars_row_label(p: dict) -> str:
    name = str(p.get("name") or "Plan").strip()
    stars = int(p.get("price_stars") or 0)
    bad = f"{name} · {_subscription_duration_badge(p.get('duration_days', 30))} · {stars}⭐"
    if len(bad) <= 64:
        return bad
    return f"{_truncate_btn(name, 32)} · {_subscription_duration_badge(p.get('duration_days', 30))} · {stars}⭐"


def _simple_stars_btn_label(p: dict) -> str:
    return f"{int(p.get('price_stars') or 0)} ⭐"


def _simple_crypto_btn_label(p: dict) -> str:
    from app.services.nowpayments_client import plan_nowpayments_usd_quote

    override = p.get("nowpayments_price_usd")
    try:
        override_f = float(override) if override is not None else None
    except (TypeError, ValueError):
        override_f = None
    quote = plan_nowpayments_usd_quote(
        price_stars=int(p.get("price_stars") or 0),
        nowpayments_price_usd=override_f if override_f and override_f > 0 else None,
    )
    billed = float(quote.get("billed_usd") or 0)
    usd = f"${billed:.0f}" if billed >= 10 else f"${billed:.2f}"
    return f"{usd} crypto"


def _plan_checkout_keyboard_rows(
    plans: list[dict],
    *,
    pack: bool = False,
    multi_term: bool = False,
) -> list[list[InlineKeyboardButton]]:
    """One row per payment option — price on the button, no catalog prose."""
    rows: list[list[InlineKeyboardButton]] = []
    star_cb = "pack_" if pack else "plan_"
    ext_cb = "ext_pack_" if pack else "ext_plan_"
    for p in plans:
        pid = int(p["id"])
        if int(p.get("price_stars") or 0) > 0:
            star_label = _subscription_stars_row_label(p) if multi_term else _simple_stars_btn_label(p)
            rows.append(
                [
                    InlineKeyboardButton(
                        _truncate_btn(star_label, 64),
                        callback_data=f"{star_cb}{pid}",
                    )
                ]
            )
        if _plan_show_crypto_checkout(p):
            crypto_label = _simple_crypto_btn_label(p)
            if multi_term:
                crypto_label = f"{crypto_label} · {_subscription_duration_badge(p.get('duration_days', 30))}"
            rows.append(
                [
                    InlineKeyboardButton(
                        _truncate_btn(crypto_label, 64),
                        callback_data=f"{ext_cb}{pid}",
                    )
                ]
            )
        if _plan_show_gumroad_checkout(p):
            gr_label = "💳 Gumroad (card)"
            if multi_term:
                gr_label = f"💳 Gumroad · {_subscription_duration_badge(p.get('duration_days', 30))}"
            rows.append(
                [
                    InlineKeyboardButton(
                        _truncate_btn(gr_label, 64),
                        callback_data=f"{'gr_pack_' if pack else 'gr_plan_'}{pid}",
                    )
                ]
            )
    return rows


def _plan_show_gumroad_checkout(p: dict) -> bool:
    try:
        from app.services.gumroad_ping import gumroad_checkout_enabled, product_url_for_plan
    except Exception:
        return False
    if not gumroad_checkout_enabled():
        return False
    try:
        pid = int(p.get("id") or 0)
    except (TypeError, ValueError):
        return False
    return bool(pid and product_url_for_plan(pid))


async def send_simple_plan_checkout(
    msg,
    context: ContextTypes.DEFAULT_TYPE,
    plans: list[dict],
    *,
    pack: bool = False,
) -> None:
    """Dead-simple checkout: product name (if any) + Stars row + crypto row per plan."""
    if not msg:
        return
    if not plans:
        await msg.reply_text("No products listed right now.")
        return
    multi_term = (not pack) and len(plans) > 1
    rows = _plan_checkout_keyboard_rows(plans, pack=pack, multi_term=multi_term)
    if not rows:
        await msg.reply_text("No checkout options for these products.")
        return
    kb = InlineKeyboardMarkup(rows)
    if len(plans) == 1:
        text = str(plans[0].get("name") or "").strip() or "·"
    elif multi_term:
        text = "💎 <b>AOF VIP</b> — same ladder as Gumroad. Pick a term:"
    else:
        text = "·"
    await msg.reply_text(text, parse_mode="HTML" if multi_term else None, reply_markup=kb)


def _subscription_wallet_row_label(p: dict, c_label: str) -> str:
    """Shorter crypto row: show billed USD when NOWPayments min floor applies."""
    from app.services.nowpayments_client import plan_nowpayments_usd_quote

    name = str(p.get("name") or "Plan").strip()
    cshort = (c_label or "Crypto").strip() or "Crypto"
    if cshort in ("USDT (TRC-20)", "USDT"):
        cshort = "USDT"
    elif len(cshort) > 10:
        cshort = cshort[:9] + "…"
    override = p.get("nowpayments_price_usd")
    try:
        override_f = float(override) if override is not None else None
    except (TypeError, ValueError):
        override_f = None
    quote = plan_nowpayments_usd_quote(
        price_stars=int(p.get("price_stars") or 0),
        nowpayments_price_usd=override_f if override_f and override_f > 0 else None,
    )
    billed = float(quote.get("billed_usd") or 0)
    usd_tag = f"${billed:.0f}" if billed >= 10 else f"${billed:.2f}"
    s = f"{usd_tag} {cshort} · {name}"
    if len(s) > 64:
        s = f"{usd_tag} {cshort} · {_truncate_btn(name, 36)}"
    return _truncate_btn(s, 64)


def _plan_show_crypto_checkout(p: dict) -> bool:
    from app.services.nowpayments_client import plan_crypto_checkout_eligible

    override = p.get("nowpayments_price_usd")
    try:
        override_f = float(override) if override is not None else None
    except (TypeError, ValueError):
        override_f = None
    return plan_crypto_checkout_eligible(
        price_stars=int(p.get("price_stars") or 0),
        nowpayments_price_usd=override_f if override_f and override_f > 0 else None,
        bot_section=str(p.get("bot_section") or "main"),
    )


async def send_subscription_catalog_message(
    msg,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    section: str = "main",
    title: str = "💎 **Premium Access**",
) -> None:
    """Subscription checkout — price on each button, no instructional catalog prose."""
    if not msg:
        return

    st = await _get_runtime_settings()
    plans = await fetch_plans(section=section, min_stars=int(st.get("min_subscription_stars") or 0))
    if not plans:
        section_hint = " (/loot section)" if section == "loot" else ""
        await msg.reply_text(
            f"No subscription plans are listed yet{section_hint}. "
            f"(Catalog source: {API_BASE.rstrip('/')}; ensure TBCC-Backend is running.)",
        )
        return

    await send_simple_plan_checkout(msg, context, plans)


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /subscribe - show plan buttons (works in DM, groups, and channels)."""
    msg = update.effective_message
    if not msg:
        return
    await send_subscription_catalog_message(msg, context, section="main")


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
    """Send one pack preview (optional promo images) + simple Stars / crypto buttons."""
    pid = p.get("id")
    promo_urls = _plan_promo_urls(p)[:10]
    cap = _bundle_caption_html(p)
    kb = InlineKeyboardMarkup(_plan_checkout_keyboard_rows([p], pack=True))
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
            await msg.reply_text(text=cap, parse_mode="HTML", reply_markup=kb)
        elif len(resolved) == 1:
            photo = resolved[0]
            await msg.reply_photo(
                photo=photo, caption=cap, parse_mode="HTML", reply_markup=kb
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
                html.escape(str(p.get("name") or "Pack")),
                parse_mode="HTML",
                reply_markup=kb,
            )
    except Exception as e:
        logger.warning("bundle detail send failed plan_id=%s: %s", pid, e)
        try:
            await msg.reply_text(text=cap, parse_mode="HTML", reply_markup=kb)
        except Exception as e2:
            logger.warning("bundle detail fallback send failed: %s", e2)


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
    c_hint = _nowpayments_currency_label(None)
    await msg.reply_text(
        f"📦 <b>Digital packs</b>\n\n"
        f"Pick a pack — then <b>Buy</b> (Stars) or <b>crypto</b> ({html.escape(c_hint)} when fixed in settings)."
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
    st = await _get_runtime_settings()
    """Inline buttons from /start menu."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    msg = query.message
    user = query.from_user
    if not msg or not user:
        return
    if query.data == "menu_shop":
        await send_shop_promo(update, context)
    elif query.data == "menu_subscribe":
        await send_subscription_catalog_message(
            msg, context, section="main", title=str(st.get("subscribe_title_main") or "💎 **Premium Access**")
        )
    elif query.data == "menu_loot":
        await send_loot_room_message(msg, context)
    elif query.data == "menu_loot_subscribe":
        await send_subscription_catalog_message(
            msg, context, section="loot", title=str(st.get("subscribe_title_loot") or "🗝 **Loot Room Access**")
        )
    elif query.data == "menu_packs":
        await send_bundle_catalog_message(msg, context)
    elif query.data == "menu_referral":
        await reply_referral(msg, user, context)
    elif query.data == "menu_status":
        await reply_status(msg, user, context)


async def handle_gumroad_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create EPO bound to this Telegram user, then open Gumroad with tbcc_ref=EPO-…"""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    user = query.from_user
    msg = query.message
    if not user or not msg:
        return

    data = query.data
    if data.startswith("gr_plan_"):
        pid = int(data.replace("gr_plan_", ""))
        want = "subscription"
    elif data.startswith("gr_pack_"):
        pid = int(data.replace("gr_pack_", ""))
        want = "bundle"
    else:
        return

    from app.services.gumroad_ping import (
        append_tbcc_ref,
        append_vip_checkout_hints,
        gumroad_checkout_enabled,
        product_url_for_plan,
        recurrence_for_plan,
    )

    if not gumroad_checkout_enabled():
        await msg.reply_text("Gumroad checkout is not enabled right now. Use Stars or crypto.")
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

    base_url = product_url_for_plan(pid)
    if not base_url:
        await msg.reply_text(
            "Gumroad product URL not configured. Set TBCC_GUMROAD_PRODUCT_URL "
            "(or TBCC_GUMROAD_PLAN_URLS) in tbcc/.env."
        )
        return

    result, order_err = await api_create_external_order(user.id, pid)
    if not result:
        hint = order_err or "Could not create a payment order."
        await msg.reply_text(f"Could not create a payment order.\n\n{hint}")
        return

    ref = (result.get("order") or {}).get("reference_code", "")
    if not str(ref).startswith("EPO-"):
        await msg.reply_text("Order created but missing EPO reference — contact admin.")
        return

    pay_url = append_tbcc_ref(base_url, str(ref))
    rec = recurrence_for_plan(plan)
    if rec:
        pay_url = append_vip_checkout_hints(pay_url, recurrence=rec)
    title = html.escape(str(plan.get("name") or "Gumroad checkout"))
    term_hint = ""
    if rec:
        term_hint = (
            f"\n3) On Gumroad choose <b>{html.escape(rec.replace('_', ' '))}</b> "
            f"to match this term\n"
        )
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(_truncate_btn("Open Gumroad → pay", 64), url=str(pay_url)[:512])]]
    )
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    body = (
        f"<b>{title}</b>\n"
        f"Order <code>{html.escape(str(ref))}</code>\n\n"
        "1) Tap <b>Open Gumroad</b> and complete payment\n"
        "2) Keep this chat open — VIP invite DMs here after Gumroad confirms"
        f"{term_hint}"
        "\n<i>Do not share this link — it is tied to your Telegram account.</i>"
    )
    try:
        await msg.reply_text(body, parse_mode="HTML", reply_markup=kb)
    except BadRequest as e:
        logger.warning("gumroad pay button message failed: %s", e)
        eu = html.escape(str(pay_url), quote=True)
        await msg.reply_text(f'{body}\n<a href="{eu}">Open Gumroad</a>', parse_mode="HTML")


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
        await msg.reply_text(
            "Product not found or inactive. If this persists, ensure TBCC-Backend is running on "
            f"{API_BASE.rstrip('/')}."
        )
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
    pay_url = result.get("crypto_pay_url")
    details = result.get("crypto_pay_details")
    if pay_url:
        label = _truncate_btn(_simple_crypto_btn_label(plan), 64)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(label, url=str(pay_url)[:512])]])
        title = html.escape(str(plan.get("name") or "Checkout"))
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        try:
            await msg.reply_text(title, parse_mode="HTML", reply_markup=kb)
        except BadRequest as e:
            logger.warning("crypto pay button message failed: %s", e)
            eu = html.escape(str(pay_url), quote=True)
            await msg.reply_text(f'{title}\n<a href="{eu}">{label}</a>', parse_mode="HTML")
        return

    header = f"<b>Order</b> <code>{html.escape(str(ref))}</code>\n\n"
    body = ""
    pay_extra = ""
    if details:
        meta0 = result.get("crypto_nowpayments_meta")
        pc = (
            (meta0.get("pay_currency") if isinstance(meta0, dict) else None)
            or (os.getenv("TBCC_NOWPAYMENTS_PAY_CURRENCY") or "").strip().lower()
            or None
        )
        c_lbl = _nowpayments_currency_label(pc)
        body = (
            f"✅ <b>Direct wallet</b> — {html.escape(c_lbl)}\n"
            "Send the <b>exact</b> amount to the address below. <i>Unlocks when confirmed.</i>"
        )
        pay_extra += "\n\n" + str(details)
    else:
        checkout_err = str(result.get("crypto_checkout_error") or "")
        quote = result.get("crypto_checkout_quote")
        quote_line = ""
        if isinstance(quote, dict):
            try:
                sent = quote.get("usd_sent_to_nowpayments")
                saved = quote.get("nowpayments_price_usd_saved")
                used = quote.get("usd_used_for_checkout")
                stars = quote.get("price_stars")
                if sent is not None and used is not None:
                    if saved is not None and float(saved) > 0:
                        src = "dashboard USD override"
                        tail = (
                            " If it still says minimum, add a few dollars to the override or try a different pay coin in NOWPayments."
                        )
                    else:
                        src = f"{stars} ⭐ → USD (no override saved)"
                        tail = (
                            " Set <b>NOWPayments price override (USD)</b> on this product and <b>Save changes</b>."
                        )
                    quote_line = (
                        f"\n\n<i>Server billed <b>${float(sent):.2f} USD</b> to NOWPayments "
                        f"(basis <b>${float(used):.2f}</b> — {html.escape(str(src))}).{tail}</i>"
                    )
            except Exception:
                quote_line = ""
        if "less than minimal" in checkout_err.lower() or "amount_minimal_error" in checkout_err.lower():
            body = (
                "⚠️ <b>Crypto amount is below the network minimum</b> for this coin.\n"
                "Raise <b>NOWPayments price override (USD)</b> on this product (e.g. +$1), or use <b>Buy</b> (Stars)."
            )
        else:
            body = (
                "⚠️ <b>Crypto checkout failed.</b>\n"
                "Use <b>Buy</b> (Telegram Stars) or the manual reference below."
            )
        pay_extra += quote_line + "\n\n" + instr
    meta = result.get("crypto_nowpayments_meta")
    if isinstance(meta, dict):
        meta_lines: list[str] = []
        if not details:
            p_usd = meta.get("price_usd")
            try:
                if p_usd is not None:
                    meta_lines.append(f"Order total: <b>${float(p_usd):.2f} USD</b>")
            except Exception:
                pass
        rw = (meta.get("receiving_wallet") or "").strip() if isinstance(meta.get("receiving_wallet"), str) else ""
        if rw:
            meta_lines.append(f"Note: <code>{html.escape(rw)}</code>")
        if meta_lines:
            pay_extra += "\n\n" + "\n".join(meta_lines)
    try:
        await msg.reply_text(header + body + pay_extra, parse_mode="HTML")
    except BadRequest as e:
        logger.warning("external order message failed: %s", e)
        await msg.reply_text(f"Order {ref} created. Check API logs if instructions did not show.")

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass


async def _send_stars_invoice(
    context: ContextTypes.DEFAULT_TYPE,
    msg,
    buyer_telegram_user_id: int,
    plan: dict,
    *,
    skip_promo: bool = False,
) -> None:
    """Send Telegram Stars invoice — works in DM, groups, and channels where the bot can post."""
    plan_id = int(plan.get("id") or 0)
    ptype = (plan.get("product_type") or "subscription").lower()
    price_stars = int(plan.get("price_stars") or 0)
    if price_stars <= 0:
        await msg.reply_text("This product has no price set.")
        return

    desc = _pick_display_description(plan) or plan_invoice_description(plan)

    invoice_payload = stars_invoice_payload(
        plan_id,
        product_type=ptype,
        user_id=buyer_telegram_user_id,
    )

    album_sent = False
    if not skip_promo:
        album_sent = await _maybe_send_promo_album_before_invoice(msg, plan)

    promo_urls = _plan_promo_urls(plan)
    promo = "" if album_sent else (promo_urls[0] if promo_urls else "")
    invoice_kw: dict = {
        "chat_id": msg.chat_id,
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
        if invoice_kw.get("photo_url") and (
            "photo" in str(e).lower() or "wrong" in str(e).lower() or "invalid" in str(e).lower()
        ):
            logger.warning("send_invoice photo rejected, retrying without photo: %s", e)
            invoice_kw.pop("photo_url", None)
            await context.bot.send_invoice(**invoice_kw)
        else:
            raise


async def handle_product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send invoice when user picks subscription (plan_) or pack (pack_)."""
    query = update.callback_query
    if not query:
        return

    if not query.data:
        await query.answer()
        return
    parts = query.data.split("_", 1)
    if len(parts) != 2:
        await query.answer()
        return
    kind, rest = parts[0], parts[1]
    if kind not in ("plan", "pack") or not rest.isdigit():
        await query.answer()
        return

    plan_id = int(rest)
    plan = await fetch_plan_by_id(plan_id)
    if not plan:
        await query.answer(
            "Catalog temporarily unavailable — is TBCC-Backend running? Tap again in a moment.",
            show_alert=True,
        )
        logger.warning("checkout callback plan_%s: catalog lookup failed (API %s)", plan_id, API_BASE)
        return

    ptype = (plan.get("product_type") or "subscription").lower()
    if kind == "plan" and ptype != "subscription":
        await query.answer("That product is no longer a subscription.", show_alert=True)
        return
    if kind == "pack" and ptype != "bundle":
        await query.answer("That product is no longer a pack.", show_alert=True)
        return

    price_stars = plan.get("price_stars", 0)
    if price_stars <= 0:
        await query.answer("This product has no Stars price set.", show_alert=True)
        return

    await query.answer()
    if not query.message:
        return
    try:
        await _send_stars_invoice(
            context, query.message, query.from_user.id, plan, skip_promo=True
        )
    except Exception as e:
        logger.exception("Stars invoice failed plan_id=%s: %s", plan_id, e)
        await query.message.reply_text(
            "Could not open the Stars invoice. Try again in a moment or use /subscribe."
        )
        return

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception as e:
        logger.debug("edit_message_reply_markup after invoice: %s", e)


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
            from app.services.aof_vip_fulfillment import vip_welcome_message_html

            text = vip_welcome_message_html(invite_link=link)
            if progress_line:
                text = f"{text}\n\n{sub.get('milestone_progress', '').strip()}"
            await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=False)
            return
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
    global _health_crypto_auto_checkout
    me = await app.bot.get_me()
    st = await _get_runtime_settings(force_refresh=True)
    logger.info("Payment bot online: @%s id=%s — /shop uses MessageHandler + promo flow", me.username, me.id)
    logger.info(
        "Payment bot runtime settings: columns=%s min_stars=%s",
        st.get("subscription_catalog_columns"),
        st.get("min_subscription_stars"),
    )
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{API_BASE.rstrip('/')}/health", timeout=10.0)
            if r.is_success:
                data = r.json()
                _health_crypto_auto_checkout = bool(data.get("crypto_auto_checkout"))
                if _health_crypto_auto_checkout:
                    logger.info("API reports crypto_auto_checkout=true (NOWPayments + HTTPS IPN path ready)")
                else:
                    logger.warning(
                        "API reports crypto_auto_checkout=false — set TBCC_NOWPAYMENTS_API_KEY, "
                        "TBCC_NOWPAYMENTS_IPN_SECRET, and TBCC_PUBLIC_API_BASE_URL (public https, no localhost) "
                        "for automatic crypto checkout + fulfillment"
                    )
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
        BotCommand("loot", "Loot Room 24h key + private group"),
        BotCommand("subscribe", "Premium — Stars, crypto & fiat"),
        BotCommand("packs", "Digital packs"),
        BotCommand("referral", "Your code, link & rewards"),
        BotCommand("status", "Your subscription & purchases"),
        BotCommand("resolve", "Unwrap supported ad/short links"),
        BotCommand("macrosearch", "Macro search + video URLs by username"),
        BotCommand("videofind", "Alias for /macrosearch"),
    ]
    try:
        await app.bot.set_my_commands(commands)
    except Exception as e:
        logger.warning("set_my_commands failed: %s", e)
    try:
        short_desc = (
            "AOF Access Bot: Loot Room keys, premium, and packs. Stars + crypto. Start with /start"
            if _health_crypto_auto_checkout
            else "AOF Access Bot: Loot Room keys, premium, and packs. Stars + Wallet/crypto. Start with /start"
        )
        await app.bot.set_my_short_description(short_desc)
    except Exception as e:
        logger.warning("set_my_short_description failed: %s", e)
    # Long profile text (“What can this bot do?”) — max 512 chars for set_my_description
    long_desc = (
        "AOF Access Bot — get Loot Room keys, premium access, and digital packs.\n\n"
        "Start with /start.\n\n"
        "• /shop — full storefront\n"
        "• /loot — Loot Room 24h key + private group flow\n"
        "• /subscribe — premium memberships\n"
        "• /packs — digital packs\n"
        "• /status — your purchases & access\n"
        "• /resolve — unwrap supported ad/short links\n"
        "• /macrosearch — macro model search + video URLs\n"
        "• /videofind — same as /macrosearch\n"
        "• /referral — your invite link + rewards\n\n"
        "Payments: Stars in Telegram + Wallet/crypto options."
    )
    if len(long_desc) > 512:
        long_desc = long_desc[:509] + "..."
    try:
        await app.bot.set_my_description(long_desc)
    except Exception as e:
        logger.warning("set_my_description failed: %s", e)


async def on_vip_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.services.aof_vip_member_sync import handle_vip_chat_member_update

    await handle_vip_chat_member_update(update, context)


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
    app.add_handler(CommandHandler("loot", cmd_loot))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("packs", cmd_packs))
    app.add_handler(CommandHandler("referral", cmd_referral))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("resolve", cmd_resolve))
    app.add_handler(CommandHandler("videofind", cmd_videofind))
    for h in build_macro_search_handlers(
        _get_runtime_settings,
        _patch_macro_custom_sources,
        _force_refresh_runtime_settings,
    ):
        app.add_handler(h)
    # Handle /subscribe in channels (CommandHandler only matches message, not channel_post)
    app.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST & filters.Regex(r"^/loot(@\w+)?\s*$"),
            cmd_loot,
        )
    )
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
        CallbackQueryHandler(handle_menu_callback, pattern=r"^menu_(shop|loot|loot_subscribe|subscribe|packs|referral|status)$")
    )
    app.add_handler(CallbackQueryHandler(handle_pick_pack_callback, pattern=r"^pick_pack_\d+$"))
    app.add_handler(CallbackQueryHandler(handle_external_payment_callback, pattern=r"^ext_(plan|pack)_\d+$"))
    app.add_handler(CallbackQueryHandler(handle_gumroad_payment_callback, pattern=r"^gr_(plan|pack)_\d+$"))
    app.add_handler(CallbackQueryHandler(handle_product_callback, pattern=r"^(plan|pack)_\d+$"))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(
        MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment),
    )
    app.add_handler(ChatMemberHandler(on_vip_chat_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_error_handler(make_error_handler("payment-bot"))

    print(
        "Payment bot running. Commands: /start, /help, /shop, /loot, /subscribe, /packs, /referral, /status, /resolve, /macrosearch, /videofind, /macroaddsource"
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=br)


if __name__ == "__main__":
    main()
