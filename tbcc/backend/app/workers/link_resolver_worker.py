"""Process link_resolver_requests rows: policy, limits, Bypass.vip call."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime

from app.database.session import SessionLocal
from app.models.link_resolver_request import LinkResolverRequest
from app.services.link_gate_unwrap import resolve_obfuscated_url
from app.services.link_resolver_limits import allow_global_window, allow_user_hourly
from app.services.link_resolver_policy import normalize_input_url, risk_level_for_url
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


def _global_limit() -> int:
    try:
        return max(1, int(os.getenv("TBCC_BYPASS_GLOBAL_MAX_PER_WINDOW", "8")))
    except ValueError:
        return 8


def _global_window() -> float:
    try:
        return max(1.0, float(os.getenv("TBCC_BYPASS_GLOBAL_WINDOW_SEC", "10")))
    except ValueError:
        return 10.0


def _user_hourly_limit(tier: str) -> int:
    key = "TBCC_LINK_RESOLVER_PREMIUM_PER_HOUR" if tier == "premium" else "TBCC_LINK_RESOLVER_FREE_PER_HOUR"
    default = "120" if tier == "premium" else "15"
    try:
        return max(0, int(os.getenv(key, default)))
    except ValueError:
        return int(default)


def _process_one(public_id: str) -> None:
    db = SessionLocal()
    try:
        row = db.query(LinkResolverRequest).filter(LinkResolverRequest.public_id == public_id).first()
        if not row:
            logger.warning("link_resolver: missing row public_id=%s", public_id)
            return
        if row.status != "queued":
            return

        row.status = "running"
        row.updated_at = datetime.utcnow()
        db.commit()

        normalized, block_reason = normalize_input_url(row.input_url)
        if block_reason:
            row.status = "blocked"
            row.reason_code = block_reason
            row.normalized_url = None
            row.updated_at = datetime.utcnow()
            db.commit()
            return

        row.normalized_url = normalized[:2048] if normalized else None
        db.commit()

        ul = _user_hourly_limit(row.tier or "free")
        if not allow_user_hourly(telegram_user_id=int(row.telegram_user_id), limit=ul):
            row.status = "failed"
            row.reason_code = "user_quota"
            row.error_detail = "Hourly limit reached. Premium users get a higher quota."
            row.updated_at = datetime.utcnow()
            db.commit()
            return

        if not allow_global_window(limit=_global_limit(), window_sec=_global_window()):
            row.status = "failed"
            row.reason_code = "global_rate_limit"
            row.error_detail = "Service busy; try again shortly."
            row.updated_at = datetime.utcnow()
            db.commit()
            return

        t0_ms = int(datetime.utcnow().timestamp() * 1000)
        final_url, err = resolve_obfuscated_url(normalized or row.input_url)
        row.provider_latency_ms = int(datetime.utcnow().timestamp() * 1000) - t0_ms
        if final_url:
            row.status = "succeeded"
            row.final_url = final_url
            row.risk_level = risk_level_for_url(row.input_url, final_url)
            row.error_detail = None
            row.reason_code = None
        else:
            row.status = "failed"
            row.reason_code = err or "resolve_failed"
            row.error_detail = (err or "resolve_failed")[:512]
        row.updated_at = datetime.utcnow()
        db.commit()
    except Exception:
        logger.exception("link_resolver: failed public_id=%s", public_id)
        try:
            row = db.query(LinkResolverRequest).filter(LinkResolverRequest.public_id == public_id).first()
            if row:
                row.status = "failed"
                row.reason_code = "internal_error"
                row.error_detail = "Worker error"
                row.updated_at = datetime.utcnow()
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


@celery.task(name="app.workers.link_resolver_worker.process_link_resolver_request")
def process_link_resolver_request(public_id: str) -> None:
    _process_one(public_id)
