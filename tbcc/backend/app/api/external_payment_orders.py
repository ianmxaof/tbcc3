"""
External (wallet / manual) payment orders: unique reference → admin marks paid → same fulfillment as Stars.

Set TBCC_INTERNAL_API_KEY and send header X-TBCC-Internal-Key from the payment bot + admin tools.
Optional: TBCC_EXTERNAL_PAY_TEMPLATE with {reference_code} {plan_name} {price_stars}
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.external_payment_order import ExternalPaymentOrder
from app.models.subscription_plan import SubscriptionPlan
from app.schemas.common import orm_to_dict
from app.services.external_payment_fulfill import fulfill_external_order
from app.services.nowpayments_client import (
    can_use_nowpayments_ipn,
    checkout_url_and_hint,
    create_payment,
    nowpayments_configured,
    public_api_base_url,
    stars_to_usd,
)

logger = logging.getLogger(__name__)

# Exposed via GET /health so you can confirm Uvicorn loaded this module (not an old process).
EXTERNAL_PAYMENT_ORDERS_IMPL = "uuid-epo-v2"


router = APIRouter()

def _gen_reference_code() -> str:
    """
    Human-memo-friendly prefix + 12 hex chars from UUID (fits String(32)).
    Collision risk is negligible vs. small-alphabet 8-char random (which could exhaust retries).
    """
    return "EPO-" + uuid.uuid4().hex[:12].upper()


def _internal_key_ok(x_tbcc_internal_key: str | None) -> bool:
    expected = (os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()
    if not expected:
        logger.warning("TBCC_INTERNAL_API_KEY not set — external payment endpoints are open (set a key in production)")
        return True
    got = (x_tbcc_internal_key or "").strip()
    return got == expected


def _require_internal(x_tbcc_internal_key: str | None = Header(None)) -> None:
    if not _internal_key_ok(x_tbcc_internal_key):
        raise HTTPException(status_code=403, detail="Invalid or missing X-TBCC-Internal-Key")


DEFAULT_PAY_TEMPLATE = """\
<b>Pay outside Telegram</b> (crypto wallet, Cash App, etc.)

<b>Your order reference</b> — put this in the memo / note:
<code>{reference_code}</code>

<b>Product:</b> {plan_name}
<b>Catalog price:</b> {price_stars} ⭐ (Telegram Stars equivalent — agree exact amount with your wallet off-platform.)

After you send payment, an admin verifies using the reference above and activates your access (same as Stars)."""


def _instructions_html(reference_code: str, plan_name: str, price_stars: int) -> str:
    tpl = (os.getenv("TBCC_EXTERNAL_PAY_TEMPLATE") or "").strip()
    if not tpl:
        tpl = DEFAULT_PAY_TEMPLATE
    safe_name = plan_name.replace("<", "&lt;").replace(">", "&gt;")
    try:
        return tpl.format(reference_code=reference_code, plan_name=safe_name, price_stars=price_stars)
    except Exception:
        return DEFAULT_PAY_TEMPLATE.format(reference_code=reference_code, plan_name=safe_name, price_stars=price_stars)


@router.get("/_impl")
def external_orders_impl_stamp():
    """
    Public dev diagnostic: which copy of this module is loaded (local checkout vs old Docker image).
    If this 404s, you are not hitting this FastAPI app. If wallet errors still mention the legacy
    allocate-reference message, that text is not from this codebase — another process likely owns :8000.
    """
    return {"impl": EXTERNAL_PAYMENT_ORDERS_IMPL, "module_file": __file__}


@router.post("/")
def create_external_order(
    data: dict = Body(...),
    db: Session = Depends(get_db),
    x_tbcc_internal_key: str | None = Header(None),
):
    """
    Create a pending external payment order (payment bot calls this when user taps Wallet / manual).
    """
    _require_internal(x_tbcc_internal_key)
    logger.info(
        "create_external_order impl=%s (legacy 'allocate reference' errors imply a different process on :8000)",
        EXTERNAL_PAYMENT_ORDERS_IMPL,
    )

    telegram_user_id = data.get("telegram_user_id")
    plan_id = data.get("plan_id")
    if telegram_user_id is None or plan_id is None:
        raise HTTPException(status_code=400, detail="telegram_user_id and plan_id required")

    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == int(plan_id)).first()
    if not plan or plan.is_active is False:
        raise HTTPException(status_code=404, detail="Plan not found or inactive")
    if (plan.price_stars or 0) <= 0:
        raise HTTPException(status_code=400, detail="Plan has no price")

    # No pre-SELECT for “free” codes: rely on UNIQUE(reference_code) + retry on rare collision only.
    max_attempts = 5
    for attempt in range(max_attempts):
        code = _gen_reference_code()
        row = ExternalPaymentOrder(
            telegram_user_id=int(telegram_user_id),
            plan_id=int(plan_id),
            reference_code=code,
            status="pending",
            created_at=datetime.utcnow(),
        )
        db.add(row)
        try:
            db.commit()
            db.refresh(row)
        except IntegrityError as e:
            db.rollback()
            raw = (str(getattr(e, "orig", e)) or str(e)).lower()
            # Extremely rare with UUID fragment; only this case is safe to retry.
            if "reference_code" in raw and attempt + 1 < max_attempts:
                continue
            logger.exception(
                "external_payment_orders: integrity error plan_id=%s attempt=%s",
                plan_id,
                attempt + 1,
            )
            if "pkey" in raw or "primary" in raw:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Database primary key error on external_payment_orders (often a PostgreSQL "
                        "sequence out of sync after a data import). On the DB run: "
                        "SELECT setval(pg_get_serial_sequence('external_payment_orders','id'), "
                        "COALESCE((SELECT MAX(id) FROM external_payment_orders), 1));"
                    ),
                ) from e
            raise HTTPException(
                status_code=400,
                detail="Could not create order (database constraint). Check API logs.",
            ) from e
        except Exception as e:
            db.rollback()
            logger.exception(
                "external_payment_orders: insert/commit failed (attempt %s) plan_id=%s",
                attempt + 1,
                plan_id,
            )
            raise HTTPException(
                status_code=500,
                detail=(
                    "Could not save payment order to the database. "
                    "Check API logs for the underlying error; often this means the "
                    "`external_payment_orders` table is missing — run "
                    "`alembic upgrade head` against DATABASE_URL."
                ),
            ) from e

        instr = _instructions_html(code, plan.name or "Product", int(plan.price_stars or 0))
        out: dict = {
            "order": orm_to_dict(row),
            "plan_name": plan.name,
            "price_stars": plan.price_stars,
            "instructions_html": instr,
        }
        # Automatic crypto checkout (IPN → /webhooks/nowpayments) when keys + public HTTPS base are set.
        if nowpayments_configured() and can_use_nowpayments_ipn():
            try:
                base = public_api_base_url()
                ipn_url = f"{base}/webhooks/nowpayments"
                usd = stars_to_usd(int(plan.price_stars or 0))
                np = create_payment(
                    order_id=code,
                    price_usd=usd,
                    order_description=(plan.name or "TBCC")[:512],
                    ipn_callback_url=ipn_url,
                )
                url, extra = checkout_url_and_hint(np)
                out["crypto_pay_url"] = url
                if extra:
                    out["crypto_pay_details"] = extra
            except Exception as e:
                logger.warning("NOWPayments checkout not created for %s: %s", code, e)
        return out

    logger.error(
        "external_payment_orders: exhausted insert attempts without success plan_id=%s",
        plan_id,
    )
    raise HTTPException(
        status_code=500,
        detail="Could not create payment order. Try again or check API logs.",
    )


@router.get("/pending")
def list_pending(
    db: Session = Depends(get_db),
    x_tbcc_internal_key: str | None = Header(None),
):
    """List pending external orders (admin / dashboard)."""
    _require_internal(x_tbcc_internal_key)
    rows = (
        db.query(ExternalPaymentOrder)
        .filter(ExternalPaymentOrder.status == "pending")
        .order_by(ExternalPaymentOrder.created_at.desc())
        .limit(200)
        .all()
    )
    out = []
    for r in rows:
        d = orm_to_dict(r)
        p = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == r.plan_id).first()
        d["plan_name"] = p.name if p else None
        d["price_stars"] = p.price_stars if p else None
        out.append(d)
    return out


@router.post("/{order_id}/mark-paid")
def mark_paid(
    order_id: int,
    db: Session = Depends(get_db),
    x_tbcc_internal_key: str | None = Header(None),
):
    """
    Admin confirms payment off-platform (legacy/manual). Prefer NOWPayments IPN or /webhooks/instant-payment for automation.
    """
    _require_internal(x_tbcc_internal_key)

    order = db.query(ExternalPaymentOrder).filter(ExternalPaymentOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "pending":
        raise HTTPException(status_code=400, detail=f"Order is not pending (status={order.status})")

    charge_id = f"manual_ext_{order.id}_{order.reference_code}"
    result = fulfill_external_order(
        db,
        order,
        payment_method="manual",
        telegram_charge_id=charge_id,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result
