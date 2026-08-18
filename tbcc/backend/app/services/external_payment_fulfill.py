"""Fulfill external (wallet/crypto) orders — same path as admin mark-paid and webhooks."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.api.subscriptions import subscription_create_from_payload
from app.models.external_payment_order import ExternalPaymentOrder
from app.services.playbook_engine import capture_conversion_for_user

logger = logging.getLogger(__name__)


def fulfill_external_order(
    db: Session,
    order: ExternalPaymentOrder,
    *,
    payment_method: str,
    telegram_charge_id: str,
    income_amount_usd: float | None = None,
    buyer_email: str | None = None,
) -> dict:
    """
    Mark order paid and create subscription / bundle fulfillment (idempotent if already paid).

    payment_method: manual | crypto | nowpayments | webhook | gumroad
    """
    if order.status == "paid":
        return {"ok": True, "idempotent": True, "external_order_id": order.id, "reference_code": order.reference_code}

    if order.status != "pending":
        return {"error": f"order_bad_status:{order.status}"}

    order.status = "paid"
    order.paid_at = datetime.utcnow()
    db.commit()

    result = subscription_create_from_payload(
        {
            "telegram_user_id": order.telegram_user_id,
            "plan_id": order.plan_id,
            "payment_method": payment_method,
            "telegram_payment_charge_id": telegram_charge_id,
            "referral_reward_days": 7,
            "external_order_id": order.id,
            "reference_code": order.reference_code,
            "income_amount_usd": income_amount_usd,
            "buyer_email": buyer_email,
        },
        db,
    )
    if result.get("error"):
        order.status = "pending"
        order.paid_at = None
        db.commit()
        return {"error": result.get("error")}

    result["external_order_id"] = order.id
    result["reference_code"] = order.reference_code

    # Conversion-learning hook: snapshot this converter's trajectory as a playbook.
    # Never blocks or fails the order — external (wallet/crypto) lane, Zelle/crypto outcome.
    try:
        capture_conversion_for_user(db, order.telegram_user_id, "private", "zelle_crypto")
    except Exception as e:  # noqa: BLE001
        logger.warning("playbook capture failed epo=%s: %s", order.id, e)

    return result
