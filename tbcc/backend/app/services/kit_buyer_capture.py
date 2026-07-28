"""Capture buyer email on purchase → Kit (ConvertKit) subscriber list."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def kit_capture_enabled() -> bool:
    return (os.getenv("TBCC_KIT_CAPTURE_ENABLED") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def kit_api_secret() -> str:
    return (os.getenv("TBCC_KIT_API_SECRET") or os.getenv("KIT_API_SECRET") or "").strip()


def normalize_buyer_email(raw: str | None) -> str | None:
    email = (raw or "").strip().lower()
    if not email or not _EMAIL_RE.match(email):
        return None
    return email


def capture_buyer_email_on_purchase(
    email: str | None,
    *,
    telegram_user_id: int | None = None,
    plan_name: str | None = None,
    payment_method: str | None = None,
    product_type: str | None = None,
) -> dict[str, Any]:
    """
    Upsert Kit subscriber. No-op when disabled or missing API secret.

    Never raises — email capture must not block fulfillment.
    """
    if not kit_capture_enabled():
        return {"ok": False, "skipped": "disabled"}
    secret = kit_api_secret()
    if not secret:
        return {"ok": False, "skipped": "no_api_secret"}

    normalized = normalize_buyer_email(email)
    if not normalized:
        return {"ok": False, "skipped": "invalid_email"}

    fields: dict[str, str] = {}
    if telegram_user_id is not None:
        fields["telegram_user_id"] = str(int(telegram_user_id))
    if plan_name:
        fields["last_plan"] = str(plan_name)[:120]
    if payment_method:
        fields["last_payment_method"] = str(payment_method)[:32]
    if product_type:
        fields["last_product_type"] = str(product_type)[:32]

    body: dict[str, Any] = {"email_address": normalized, "state": "active"}
    if fields:
        body["fields"] = fields

    tag_id = (os.getenv("TBCC_KIT_PURCHASE_TAG_ID") or "").strip()
    if tag_id.isdigit():
        body["tags"] = [int(tag_id)]

    try:
        resp = httpx.post(
            "https://api.kit.com/v4/subscribers",
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=body,
            timeout=12.0,
        )
        if resp.status_code in (200, 201):
            return {"ok": True, "email": normalized}
        logger.warning(
            "Kit capture failed status=%s body=%s",
            resp.status_code,
            (resp.text or "")[:300],
        )
        return {"ok": False, "error": f"http_{resp.status_code}"}
    except Exception as exc:
        logger.warning("Kit capture error: %s", exc)
        return {"ok": False, "error": str(exc)[:200]}
