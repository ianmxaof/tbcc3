"""Instant admin alerts for checkout intent (pending EPO) and completed sales (any payment path)."""

from __future__ import annotations

import html
import logging
import os
from typing import Any

import httpx

from app.services.outbound_webhook import notify_outbound_webhook

logger = logging.getLogger(__name__)


def _notify_disabled() -> bool:
    v = (os.getenv("TBCC_PAYMENT_NOTIFY") or "").strip().lower()
    return v in ("0", "false", "no", "off")


def _admin_telegram_id() -> int | None:
    raw = (os.getenv("ADMIN_TELEGRAM_ID") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _bot_token() -> str:
    return (
        (os.getenv("TBCC_SALES_NOTIFY_BOT_TOKEN") or "").strip()
        or (os.getenv("BOT_TOKEN") or "").strip()
    )


def _telegram_send_html(text: str) -> None:
    if _notify_disabled():
        return
    chat_id = _admin_telegram_id()
    token = _bot_token()
    if not chat_id or not token:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text[:4096],
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            if r.status_code >= 400:
                logger.warning("payment notify Telegram HTTP %s: %s", r.status_code, (r.text or "")[:300])
    except Exception as e:
        logger.warning("payment notify Telegram failed: %s", e)


def _webhook(event: str, payload: dict[str, Any]) -> None:
    hook = (os.getenv("TBCC_SALES_NOTIFY_WEBHOOK_URL") or "").strip()
    if not hook:
        return
    notify_outbound_webhook(hook, {"event": event, **payload})


def notify_epo_pending(
    *,
    reference_code: str,
    telegram_user_id: int,
    plan_name: str,
    price_stars: int,
) -> None:
    """Someone tapped crypto / external checkout — payment may not have cleared yet."""
    try:
        payload = {
            "reference_code": reference_code,
            "telegram_user_id": telegram_user_id,
            "plan_name": plan_name,
            "price_stars": price_stars,
        }
        _webhook("epo_pending", payload)
        pn = html.escape(plan_name or "Product")
        ref = html.escape(reference_code)
        body = (
            "<b>Pending wallet / crypto checkout</b>\n"
            "Buyer started external pay — confirm funds or wait for NOWPayments IPN.\n\n"
            f"Ref: <code>{ref}</code>\n"
            f"Buyer TG: <code>{telegram_user_id}</code>\n"
            f"Product: {pn}\n"
            f"Catalog: {int(price_stars)} ⭐\n\n"
            "<i>Fulfillment is automatic when IPN hits <code>/webhooks/nowpayments</code>, "
            "or use dashboard <b>Mark paid</b> after you verify payment.</i>"
        )
        _telegram_send_html(body)
    except Exception as e:
        logger.warning("notify_epo_pending failed: %s", e)


def notify_sale_fulfilled(
    *,
    telegram_user_id: int,
    plan_name: str,
    product_type: str | None,
    payment_method: str | None,
) -> None:
    """Access was granted (Stars, crypto IPN, webhook, or manual mark-paid)."""
    try:
        pm = (payment_method or "?").strip() or "?"
        ptype = (product_type or "").strip() or "subscription"
        payload = {
            "telegram_user_id": telegram_user_id,
            "plan_name": plan_name,
            "product_type": ptype,
            "payment_method": pm,
        }
        _webhook("sale_fulfilled", payload)
        pn = html.escape(plan_name or "Product")
        body = (
            "<b>Sale / access granted</b>\n"
            f"Product: {pn} ({html.escape(ptype)})\n"
            f"Buyer TG: <code>{telegram_user_id}</code>\n"
            f"Payment: <code>{html.escape(pm)}</code>"
        )
        _telegram_send_html(body)
    except Exception as e:
        logger.warning("notify_sale_fulfilled failed: %s", e)
