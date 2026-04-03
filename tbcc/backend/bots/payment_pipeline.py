"""
In-bot Telegram Stars payment pipeline helpers.

- Parse invoice_payload from send_invoice (sub_{plan_id}_{user_id} / bundle_...)
- Validate PreCheckoutQuery (user, currency XTR, amount vs catalog, product still active)
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Any

logger = logging.getLogger(__name__)

# Telegram limits pre_checkout error_message length
MAX_PRECHECKOUT_ERROR = 64


def _truncate(msg: str) -> str:
    if len(msg) <= MAX_PRECHECKOUT_ERROR:
        return msg
    return msg[: MAX_PRECHECKOUT_ERROR - 1] + "…"


def parse_invoice_payload(payload: str | None) -> tuple[str, int, int] | None:
    """
    Returns (kind, plan_id, user_id) where kind is 'sub' or 'bundle'.
    Expected: sub_{plan_id}_{user_id} or bundle_{plan_id}_{user_id}
    """
    if not payload:
        return None
    parts = payload.split("_")
    if len(parts) != 3:
        return None
    kind_raw, plan_s, user_s = parts
    if kind_raw not in ("sub", "bundle"):
        return None
    try:
        return kind_raw, int(plan_s), int(user_s)
    except ValueError:
        return None


def product_matches_kind(kind: str, product_type: str | None) -> bool:
    pt = (product_type or "subscription").lower()
    if kind == "sub":
        return pt == "subscription"
    if kind == "bundle":
        return pt == "bundle"
    return False


async def validate_pre_checkout(
    query: Any,
    fetch_plan_by_id: Callable[[int], Awaitable[dict | None]],
) -> tuple[bool, str | None]:
    """
    Validate Stars invoice before Telegram collects payment.
    Returns (ok, error_message). error_message must be short (Telegram max 64 chars).
    """
    payload = getattr(query, "invoice_payload", None) or ""
    parsed = parse_invoice_payload(payload)
    if not parsed:
        return False, _truncate("Invalid invoice. Open /shop and try again.")

    kind, plan_id, user_id = parsed
    buyer = getattr(query, "from_user", None)
    if not buyer or buyer.id != user_id:
        return False, _truncate("This payment is tied to another account.")

    currency = (getattr(query, "currency", None) or "").upper()
    if currency != "XTR":
        return False, _truncate("Only Telegram Stars are accepted.")

    plan = await fetch_plan_by_id(plan_id)
    if not plan:
        return False, _truncate("Product unavailable. Try /shop again.")
    if plan.get("is_active") is False:
        return False, _truncate("Product unavailable. Try /shop again.")
    if not product_matches_kind(kind, plan.get("product_type")):
        return False, _truncate("Product unavailable. Try /shop again.")

    stars = int(plan.get("price_stars") or 0)
    if stars <= 0:
        return False, _truncate("Invalid product price.")

    total = int(getattr(query, "total_amount", 0) or 0)
    if total != stars:
        logger.warning(
            "pre_checkout amount mismatch plan=%s expected=%s got=%s",
            plan_id,
            stars,
            total,
        )
        return False, _truncate("Price updated — open /shop again.")

    return True, None
