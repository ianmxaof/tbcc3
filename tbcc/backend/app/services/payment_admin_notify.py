"""
Instant admin alerts for checkout intent (pending EPO) and completed sales (any payment path).

Notification policy (see also admin_inbox.py):
- **Instant Telegram DM (important):** completed sales (Stars, crypto IPN, manual mark-paid), pending
  manual wallet checkout, ops critical/important (errors, bottlenecks, conflicts).
- **Inbox only (analytics / secondary):** loot referral signups, growth attribution, non-urgent loot info.

Instant DMs use TBCC_SECRETARY_BOT_TOKEN + ADMIN_TELEGRAM_ID via HTTP — the secretary_bot *process*
does not need to be running for sale/error pings (only for /inbox digests and inline callbacks).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.services.admin_inbox import push_admin_inbox_event
from app.services.outbound_webhook import notify_outbound_webhook

logger = logging.getLogger(__name__)


def _notify_disabled() -> bool:
    v = (os.getenv("TBCC_PAYMENT_NOTIFY") or "").strip().lower()
    return v in ("0", "false", "no", "off")


def sales_instant_enabled() -> bool:
    """Completed sales ping Telegram instantly (default on)."""
    return (os.getenv("TBCC_INBOX_INSTANT_SALES") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _webhook(event: str, payload: dict[str, Any]) -> None:
    hook = (os.getenv("TBCC_SALES_NOTIFY_WEBHOOK_URL") or "").strip()
    if not hook:
        return
    notify_outbound_webhook(hook, {"event": event, **payload})


def classify_sale_kind(
    *,
    product_type: str | None,
    bot_section: str | None = None,
    plan_name: str | None = None,
) -> str:
    """loot_key | pack | subscription"""
    ptype = (product_type or "").strip().lower()
    section = (bot_section or "").strip().lower()
    name = (plan_name or "").lower()
    if ptype == "bundle":
        return "pack"
    if section == "loot" or "loot room" in name or "24h" in name:
        return "loot_key"
    if section == "packs" or "pack" in name:
        return "pack"
    return "subscription"


def _payment_method_label(payment_method: str | None) -> str:
    pm = (payment_method or "").strip().lower()
    if pm in ("stars", "telegram_stars"):
        return "Telegram Stars"
    if pm in ("nowpayments", "crypto", "webhook"):
        return "Crypto (NOWPayments)"
    if pm == "manual":
        return "Manual wallet"
    if pm:
        return pm
    return "unknown"


def _sale_title(*, sale_kind: str, payment_method: str | None) -> str:
    pm = (payment_method or "").strip().lower()
    if pm in ("stars", "telegram_stars"):
        pay_tag = "Stars"
    elif pm in ("nowpayments", "crypto", "webhook"):
        pay_tag = "Crypto"
    elif pm == "manual":
        pay_tag = "Manual"
    else:
        pay_tag = _payment_method_label(payment_method)

    kind_titles = {
        "loot_key": f"Loot key sold ({pay_tag})",
        "pack": f"Pack sold ({pay_tag})",
        "subscription": f"Subscription sold ({pay_tag})",
    }
    return kind_titles.get(sale_kind, f"Sale completed ({pay_tag})")


def notify_epo_pending(
    *,
    reference_code: str,
    telegram_user_id: int,
    plan_name: str,
    price_stars: int,
    order_id: int | None = None,
    crypto_auto_checkout: bool = False,
    bot_section: str | None = None,
    product_type: str | None = None,
) -> None:
    """Someone tapped crypto / external checkout — payment may not have cleared yet."""
    if _notify_disabled():
        return
    try:
        sale_kind = classify_sale_kind(
            product_type=product_type,
            bot_section=bot_section,
            plan_name=plan_name,
        )
        payload = {
            "reference_code": reference_code,
            "telegram_user_id": telegram_user_id,
            "plan_name": plan_name,
            "price_stars": price_stars,
            "order_id": order_id,
            "crypto_auto_checkout": crypto_auto_checkout,
            "sale_kind": sale_kind,
            "event_type": "checkout_pending",
        }
        _webhook("epo_pending", payload)
        push_admin_inbox_event(
            category="invoice",
            severity="important",
            title=f"Pending checkout · {plan_name}",
            body=(
                f"Buyer TG {telegram_user_id} started checkout for {plan_name} ({int(price_stars)} stars).\n"
                f"Ref: {reference_code}\n\n"
                "What to do:\n"
                + (
                    "Wait for crypto IPN to auto-fulfill — no action unless it stalls."
                    if crypto_auto_checkout
                    else "Verify payment in wallet, then tap Approve below (or Deny if spam)."
                )
            ),
            meta=payload,
            instant=not crypto_auto_checkout,
        )
    except Exception as e:
        logger.warning("notify_epo_pending failed: %s", e)


def notify_sale_fulfilled(
    *,
    telegram_user_id: int,
    plan_name: str,
    product_type: str | None,
    payment_method: str | None,
    amount_stars: int | None = None,
    bot_section: str | None = None,
    plan_id: int | None = None,
    external_order_id: int | None = None,
    reference_code: str | None = None,
) -> None:
    """Access was granted (Stars, crypto IPN, webhook, or manual mark-paid)."""
    if _notify_disabled():
        return
    try:
        pm = (payment_method or "?").strip() or "?"
        ptype = (product_type or "").strip() or "subscription"
        sale_kind = classify_sale_kind(
            product_type=ptype,
            bot_section=bot_section,
            plan_name=plan_name,
        )
        stars = int(amount_stars or 0)
        payload: dict[str, Any] = {
            "telegram_user_id": telegram_user_id,
            "plan_name": plan_name,
            "product_type": ptype,
            "payment_method": pm,
            "payment_method_label": _payment_method_label(pm),
            "amount_stars": stars,
            "bot_section": (bot_section or "").strip() or None,
            "sale_kind": sale_kind,
            "event_type": "sale_fulfilled",
        }
        if plan_id is not None:
            payload["plan_id"] = int(plan_id)
        if external_order_id is not None:
            payload["external_order_id"] = int(external_order_id)
        if reference_code:
            payload["reference_code"] = reference_code

        _webhook("sale_fulfilled", payload)
        push_admin_inbox_event(
            category="payment",
            severity="important",
            title=_sale_title(sale_kind=sale_kind, payment_method=pm),
            body=(
                f"{plan_name} · buyer TG {telegram_user_id} · {stars} stars · {_payment_method_label(pm)}\n\n"
                "What to do:\nNo action needed — access was granted automatically."
            ),
            meta=payload,
            instant=sales_instant_enabled(),
        )
    except Exception as e:
        logger.warning("notify_sale_fulfilled failed: %s", e)
