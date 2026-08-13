"""Telegram Stars (XTR) invoice helpers — send_invoice + createInvoiceLink."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from app.utils.telegram_promo_url import is_public_https_for_telegram

logger = logging.getLogger(__name__)

# Shareable invoice links (createInvoiceLink) use user_id=0 in payload; pre_checkout binds buyer.
INVOICE_LINK_USER_ID = 0

_INVOICE_LINK_CACHE: dict[int, tuple[str, float]] = {}
_INVOICE_LINK_CACHE_TTL_SEC = 3600


def use_invoice_link_checkout() -> bool:
    raw = (os.getenv("TBCC_CHECKOUT_USE_INVOICE_LINK") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def stars_invoice_payload(
    plan_id: int,
    *,
    product_type: str | None,
    user_id: int,
) -> str:
    ptype = (product_type or "subscription").lower()
    if ptype == "bundle":
        kind = "bundle"
    elif ptype == "companion_credits":
        kind = "credits"
    else:
        kind = "sub"
    return f"{kind}_{int(plan_id)}_{int(user_id)}"


def plan_invoice_description(plan: dict) -> str:
    desc = str(plan.get("description") or plan.get("bot_description") or "").strip()
    if desc:
        return desc[:255]
    ptype = (plan.get("product_type") or "subscription").lower()
    if ptype == "bundle":
        return "Digital pack — images & videos"
    if ptype == "companion_credits":
        return "Companion photo reveal credits — @aof_spicybot_bot"
    days = int(plan.get("duration_days") or 30)
    return f"Subscription — {days} days access"


def plan_promo_photo_url(plan: dict) -> str | None:
    urls = plan.get("promo_image_urls") or plan.get("promo_urls") or []
    if isinstance(urls, str):
        urls = [urls]
    for raw in urls:
        u = str(raw or "").strip()
        if is_public_https_for_telegram(u):
            return u
    return None


def _bot_token() -> str:
    return (os.getenv("BOT_TOKEN") or os.getenv("TBCC_PAYMENT_BOT_TOKEN") or "").strip()


def create_stars_invoice_link(
    plan: dict,
    *,
    user_id: int = INVOICE_LINK_USER_ID,
    force_refresh: bool = False,
) -> str | None:
    """
    Telegram createInvoiceLink — opens native Stars payment UI in one tap (channels/groups/DM).
    Cached per plan_id for TBCC_CHECKOUT_INVOICE_LINK_CACHE_SEC (default 1h).
    """
    if not use_invoice_link_checkout():
        return None

    plan_id = int(plan.get("id") or 0)
    if plan_id <= 0:
        return None

    stars = int(plan.get("price_stars") or 0)
    if stars <= 0:
        return None

    ttl = int(os.getenv("TBCC_CHECKOUT_INVOICE_LINK_CACHE_SEC") or _INVOICE_LINK_CACHE_TTL_SEC)
    now = time.time()
    if not force_refresh:
        cached = _INVOICE_LINK_CACHE.get(plan_id)
        if cached and (now - cached[1]) < ttl:
            return cached[0]

    token = _bot_token()
    if not token:
        logger.warning("create_stars_invoice_link: BOT_TOKEN unset")
        return None

    title = str(plan.get("name") or "Product")[:32]
    description = plan_invoice_description(plan)
    payload = stars_invoice_payload(
        plan_id,
        product_type=plan.get("product_type"),
        user_id=user_id,
    )
    body: dict[str, Any] = {
        "title": title,
        "description": description[:255],
        "payload": payload[:128],
        "currency": "XTR",
        "prices": [{"label": title[:64], "amount": stars}],
    }
    photo = plan_promo_photo_url(plan)
    if photo:
        body["photo_url"] = photo

    url = f"https://api.telegram.org/bot{token}/createInvoiceLink"
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, json=body)
            data = r.json()
    except Exception as e:
        logger.exception("createInvoiceLink failed plan_id=%s: %s", plan_id, e)
        return None

    if not data.get("ok"):
        err = data.get("description") or data
        logger.warning("createInvoiceLink rejected plan_id=%s: %s", plan_id, err)
        if photo:
            body.pop("photo_url", None)
            try:
                with httpx.Client(timeout=30.0) as client:
                    r = client.post(url, json=body)
                    data = r.json()
            except Exception as e:
                logger.exception("createInvoiceLink retry failed plan_id=%s: %s", plan_id, e)
                return None
            if not data.get("ok"):
                logger.warning(
                    "createInvoiceLink retry rejected plan_id=%s: %s",
                    plan_id,
                    data.get("description") or data,
                )
                return None
        else:
            return None

    link = str(data.get("result") or "").strip()
    if not link:
        return None
    _INVOICE_LINK_CACHE[plan_id] = (link, now)
    return link


def plan_to_invoice_link_dict(plan: Any) -> dict:
    """ORM SubscriptionPlan → dict for create_stars_invoice_link."""
    if isinstance(plan, dict):
        return plan
    return {
        "id": plan.id,
        "name": plan.name,
        "description": getattr(plan, "description", None),
        "bot_description": getattr(plan, "bot_description", None),
        "product_type": getattr(plan, "product_type", None),
        "price_stars": plan.price_stars,
        "duration_days": getattr(plan, "duration_days", None),
        "promo_image_urls": getattr(plan, "promo_image_urls", None),
    }
