"""
Automatic fulfillment for external (non–Telegram-Stars) checkouts.

- POST /webhooks/nowpayments — NOWPayments IPN (HMAC-SHA512); set TBCC_NOWPAYMENTS_IPN_SECRET.
- POST /webhooks/instant-payment — generic Bearer TBCC_PAYMENT_WEBHOOK_SECRET + JSON { "reference_code": "EPO-…" }.
- POST /webhooks/gumroad — Gumroad Ping (form-urlencoded sale); set TBCC_GUMROAD_SELLER_ID.

Telegram Stars remain instant via the bot’s successful_payment handler (no webhook here).
"""

from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.external_payment_order import ExternalPaymentOrder
from app.services.external_payment_fulfill import fulfill_external_order
from app.services.nowpayments_client import payment_done_status, verify_ipn_signature

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/nowpayments")
async def nowpayments_ipn(request: Request, db: Session = Depends(get_db)):
    """NOWPayments posts here when payment status changes; we fulfill on finished."""
    secret = (os.getenv("TBCC_NOWPAYMENTS_IPN_SECRET") or "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="TBCC_NOWPAYMENTS_IPN_SECRET not configured")

    body_bytes = await request.body()
    try:
        data = json.loads(body_bytes.decode("utf-8") or "{}")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="invalid json") from e
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="invalid body")

    sig = request.headers.get("x-nowpayments-sig") or request.headers.get("X-NOWPAYMENTS-SIG")
    if not verify_ipn_signature(data, sig, secret, raw_body=body_bytes):
        raise HTTPException(status_code=403, detail="invalid signature")

    if not payment_done_status(data.get("payment_status")):
        return {"ok": True, "ignored": "payment_status", "status": data.get("payment_status")}

    ref = data.get("order_id")
    if not ref:
        return {"ok": True, "ignored": "no_order_id"}

    order = db.query(ExternalPaymentOrder).filter(ExternalPaymentOrder.reference_code == str(ref)).first()
    if not order:
        logger.warning("NOWPayments IPN: unknown order_id=%s", ref)
        return {"ok": True, "ignored": "unknown_order"}

    np_id = data.get("payment_id")
    charge_id = f"np_{np_id}_{order.reference_code}" if np_id is not None else f"np_{order.reference_code}"

    income_usd: float | None = None
    for key in ("price_amount", "actually_paid", "pay_amount"):
        raw = data.get(key)
        if raw is None:
            continue
        try:
            income_usd = float(raw)
            break
        except (TypeError, ValueError):
            continue

    result = fulfill_external_order(
        db,
        order,
        payment_method="crypto",
        telegram_charge_id=str(charge_id)[:128],
        income_amount_usd=income_usd,
    )
    if result.get("error"):
        logger.error("NOWPayments fulfill failed: %s", result.get("error"))
        raise HTTPException(status_code=500, detail=str(result.get("error")))
    if result.get("idempotent"):
        return {"ok": True, "idempotent": True, "order_id": order.id}
    return {"ok": True, "fulfilled": order.id}


@router.post("/instant-payment")
async def instant_payment_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Generic automation: any system that can POST JSON when payment clears.
    Authorization: Bearer <TBCC_PAYMENT_WEBHOOK_SECRET>
    Body: { "reference_code": "EPO-XXXXXXXXXXXX" }
    """
    secret = (os.getenv("TBCC_PAYMENT_WEBHOOK_SECRET") or "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="TBCC_PAYMENT_WEBHOOK_SECRET not configured")

    auth = (request.headers.get("Authorization") or "").strip()
    if auth != f"Bearer {secret}":
        raise HTTPException(status_code=403, detail="invalid authorization")

    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="invalid json") from e
    ref = (body.get("reference_code") or "").strip()
    if not ref.startswith("EPO-"):
        raise HTTPException(status_code=400, detail="reference_code must be an EPO-… code")

    order = db.query(ExternalPaymentOrder).filter(ExternalPaymentOrder.reference_code == ref).first()
    if not order:
        raise HTTPException(status_code=404, detail="order not found")

    result = fulfill_external_order(
        db,
        order,
        payment_method="webhook",
        telegram_charge_id=f"webhook_{ref}"[:128],
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=str(result.get("error")))
    return {"ok": True, "result": result}


@router.post("/gumroad")
async def gumroad_ping(request: Request, db: Session = Depends(get_db)):
    """
    Gumroad Settings → Advanced → Ping URL:

      https://<your-public-api>/webhooks/gumroad

    Requires ``TBCC_GUMROAD_SELLER_ID`` matching the ping ``seller_id``.
    Prefer checkout via payment bot so ``tbcc_ref=EPO-…`` is on the product URL.
    """
    from app.api.subscriptions import subscription_create_from_payload
    from app.services import gumroad_ping as gr

    if not gr.gumroad_seller_id():
        raise HTTPException(status_code=503, detail="TBCC_GUMROAD_SELLER_ID not configured")

    content_type = (request.headers.get("content-type") or "").lower()
    payload: dict = {}
    if "application/json" in content_type:
        try:
            body = await request.json()
            payload = body if isinstance(body, dict) else {}
        except Exception as e:
            raise HTTPException(status_code=400, detail="invalid json") from e
    else:
        form = await request.form()
        payload = gr.form_body_to_dict(form)

    if not gr.verify_seller(payload):
        logger.warning("Gumroad ping: seller_id mismatch")
        raise HTTPException(status_code=403, detail="invalid seller_id")

    skip = gr.is_refunded_or_test_skip(payload)
    if skip:
        return {"ok": True, "ignored": skip}

    ref = gr.extract_tbcc_ref(payload)
    if ref:
        order = (
            db.query(ExternalPaymentOrder)
            .filter(ExternalPaymentOrder.reference_code == ref)
            .first()
        )
        if not order:
            logger.warning("Gumroad ping: unknown EPO %s", ref)
            return {"ok": True, "ignored": "unknown_order", "reference_code": ref}

        result = fulfill_external_order(
            db,
            order,
            payment_method="gumroad",
            telegram_charge_id=gr.sale_charge_id(payload, ref),
            income_amount_usd=gr.income_usd_from_payload(payload),
            buyer_email=gr.extract_buyer_email(payload),
        )
        if result.get("error"):
            logger.error("Gumroad fulfill failed: %s", result.get("error"))
            raise HTTPException(status_code=500, detail=str(result.get("error")))
        if result.get("idempotent"):
            return {"ok": True, "idempotent": True, "order_id": order.id, "reference_code": ref}
        return {"ok": True, "fulfilled": order.id, "reference_code": ref, "path": "epo"}

    # Fallback: custom field Telegram ID + product → plan map (no pre-created EPO)
    tg_id = gr.extract_telegram_user_id(payload)
    plan_id = gr.resolve_plan_id_from_payload(payload)
    if not tg_id or not plan_id:
        logger.info(
            "Gumroad ping: no EPO and incomplete fallback (tg_id=%s plan_id=%s email=%s)",
            tg_id,
            plan_id,
            payload.get("email"),
        )
        return {
            "ok": True,
            "ignored": "no_tbcc_ref_or_telegram_id",
            "hint": "Start checkout from @aofsubscriptions_bot (card checkout button) so tbcc_ref=EPO-… is set",
        }

    charge = gr.sale_charge_id(payload)
    result = subscription_create_from_payload(
        {
            "telegram_user_id": tg_id,
            "plan_id": plan_id,
            "payment_method": "gumroad",
            "telegram_payment_charge_id": charge,
            "referral_reward_days": 7,
            "income_amount_usd": gr.income_usd_from_payload(payload),
            "buyer_email": gr.extract_buyer_email(payload),
        },
        db,
    )
    if result.get("error"):
        # Duplicate charge_id → treat as idempotent success
        err = str(result.get("error"))
        if "duplicate" in err.lower() or "already" in err.lower():
            return {"ok": True, "idempotent": True, "path": "direct", "telegram_user_id": tg_id}
        raise HTTPException(status_code=400, detail=err)
    return {
        "ok": True,
        "fulfilled": True,
        "path": "direct",
        "telegram_user_id": tg_id,
        "plan_id": plan_id,
        "result": result,
    }
