"""
Link resolver (Bypass.vip): create async jobs and poll results.

Requires X-TBCC-Internal-Key (same as payment bot). Tier is derived from DB subscriptions.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.external_payment_orders import _require_internal
from app.database.session import get_db
from app.models.link_resolver_request import LinkResolverRequest
from app.schemas.common import orm_to_dict
from app.services.bypass_vip_client import bypass_configured
from app.services.link_resolver_tier import effective_link_resolver_tier

logger = logging.getLogger(__name__)

router = APIRouter()


class LinkResolverCreateBody(BaseModel):
    telegram_user_id: int = Field(..., ge=1)
    url: str = Field(..., min_length=1, max_length=8192)


def _enqueue(public_id: str, tier: str) -> None:
    from app.workers.link_resolver_worker import process_link_resolver_request

    queue = "link_priority" if tier == "premium" else "link"
    try:
        process_link_resolver_request.apply_async(args=[public_id], queue=queue)
    except Exception as e:
        logger.exception("link_resolver enqueue failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail="Could not queue resolver job (Redis/Celery?). Start a worker with -Q link,link_priority.",
        ) from e


@router.get("/_config")
def link_resolver_config(_: None = Depends(_require_internal)):
    """Whether bypass is enabled and key present (no secret values)."""
    enabled = (os.getenv("TBCC_BYPASS_ENABLED") or "1").strip().lower() not in ("0", "false", "no")
    return {
        "bypass_configured": bypass_configured(),
        "bypass_enabled_flag": enabled,
    }


@router.post("/requests")
def create_request(
    body: LinkResolverCreateBody,
    db: Session = Depends(get_db),
    _: None = Depends(_require_internal),
):
    if not bypass_configured():
        raise HTTPException(
            status_code=503,
            detail="Link resolver disabled: set TBCC_BYPASS_API_KEY (and TBCC_BYPASS_ENABLED=1).",
        )
    tier = effective_link_resolver_tier(db, body.telegram_user_id)
    public_id = str(uuid.uuid4())
    now = datetime.utcnow()
    row = LinkResolverRequest(
        public_id=public_id,
        telegram_user_id=body.telegram_user_id,
        tier=tier,
        input_url=body.url.strip(),
        status="queued",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    _enqueue(public_id, tier)
    return {"request": orm_to_dict(row)}


@router.get("/requests/{public_id}")
def get_request(
    public_id: str,
    db: Session = Depends(get_db),
    x_tbcc_internal_key: str | None = Header(None, alias="X-TBCC-Internal-Key"),
    telegram_user_id: int | None = Query(None, ge=1),
):
    """Optional telegram_user_id ensures callers only read their own job."""
    from app.api.external_payment_orders import _internal_key_ok

    if not _internal_key_ok(x_tbcc_internal_key):
        raise HTTPException(status_code=403, detail="Invalid or missing X-TBCC-Internal-Key")
    row = db.query(LinkResolverRequest).filter(LinkResolverRequest.public_id == public_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if telegram_user_id is not None and int(row.telegram_user_id) != int(telegram_user_id):
        raise HTTPException(status_code=404, detail="Not found")
    return {"request": orm_to_dict(row)}


@router.get("/history")
def history(
    db: Session = Depends(get_db),
    x_tbcc_internal_key: str | None = Header(None, alias="X-TBCC-Internal-Key"),
    telegram_user_id: int = Query(..., ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    from app.api.external_payment_orders import _internal_key_ok

    if not _internal_key_ok(x_tbcc_internal_key):
        raise HTTPException(status_code=403, detail="Invalid or missing X-TBCC-Internal-Key")
    q = (
        db.query(LinkResolverRequest)
        .filter(LinkResolverRequest.telegram_user_id == telegram_user_id)
        .order_by(LinkResolverRequest.created_at.desc())
        .limit(limit)
    )
    return {"requests": [orm_to_dict(r) for r in q.all()]}
