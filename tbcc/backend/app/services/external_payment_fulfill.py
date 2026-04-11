"""Fulfill external (wallet/crypto) orders — same path as admin mark-paid and webhooks."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.api.subscriptions import subscription_create_from_payload
from app.models.external_payment_order import ExternalPaymentOrder

logger = logging.getLogger(__name__)


def fulfill_external_order(
    db: Session,
    order: ExternalPaymentOrder,
    *,
    payment_method: str,
    telegram_charge_id: str,
) -> dict:
    """
    Mark order paid and create subscription / bundle fulfillment (idempotent if already paid).

    payment_method: manual | crypto | nowpayments | webhook
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
    return result
