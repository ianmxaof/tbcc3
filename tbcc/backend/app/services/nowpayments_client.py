"""NOWPayments: create crypto checkout + verify IPN (HMAC-SHA512)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

NP_API = "https://api.nowpayments.io/v1"


def nowpayments_configured() -> bool:
    return bool((os.getenv("TBCC_NOWPAYMENTS_API_KEY") or "").strip())


def public_api_base_url() -> str:
    """HTTPS base for IPN callbacks (no trailing slash)."""
    return (os.getenv("TBCC_PUBLIC_API_BASE_URL") or os.getenv("TBCC_PROMO_PUBLIC_BASE_URL") or "").strip().rstrip("/")


def can_use_nowpayments_ipn() -> bool:
    """NOWPayments requires a public https URL for ipn_callback_url (not localhost)."""
    u = public_api_base_url()
    if not u:
        return False
    if not u.startswith("https://"):
        return False
    low = u.lower()
    if "127.0.0.1" in low or "localhost" in low:
        return False
    return True


def stars_to_usd(price_stars: int) -> float:
    per = float(os.getenv("TBCC_STARS_USD_PER_STAR", "0.012"))
    return max(0.01, round(max(0, int(price_stars)) * per, 2))


def verify_ipn_signature(
    body: dict[str, Any],
    signature_header: str | None,
    secret: str,
    raw_body: bytes | None = None,
) -> bool:
    """IPN: try raw body first (common), then sorted JSON (per NOWPayments docs)."""
    if not secret or not signature_header:
        return False
    sig = signature_header.strip().lower()
    if raw_body:
        expected_raw = hmac.new(secret.encode(), raw_body, hashlib.sha512).hexdigest()
        if hmac.compare_digest(expected_raw.lower(), sig):
            return True
    sorted_str = json.dumps(body, sort_keys=True, separators=(",", ":"))
    expected = hmac.new(secret.encode(), sorted_str.encode(), hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected.lower(), sig)


def create_payment(
    *,
    order_id: str,
    price_usd: float,
    order_description: str,
    ipn_callback_url: str,
) -> dict[str, Any]:
    """
    POST /v1/payment — returns API JSON (includes invoice_url or payment id + pay_address).
    """
    key = (os.getenv("TBCC_NOWPAYMENTS_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("TBCC_NOWPAYMENTS_API_KEY not set")

    pay_currency = (os.getenv("TBCC_NOWPAYMENTS_PAY_CURRENCY") or "usdttrc20").strip()
    payload = {
        "price_amount": price_usd,
        "price_currency": "usd",
        "pay_currency": pay_currency,
        "ipn_callback_url": ipn_callback_url,
        "order_id": order_id,
        "order_description": (order_description or "TBCC order")[:512],
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                f"{NP_API}/payment",
                headers={"x-api-key": key, "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = (e.response.text or "")[:400]
        except Exception:
            pass
        logger.warning("NOWPayments create payment failed: %s %s", e.response.status_code, detail)
        raise RuntimeError(f"NOWPayments error {e.response.status_code}") from e


def payment_done_status(payment_status: str | None) -> bool:
    s = (payment_status or "").lower().strip()
    # finished = fully paid per NOWPayments docs
    return s in ("finished", "confirmed")


def checkout_url_and_hint(np: dict[str, Any]) -> tuple[str | None, str | None]:
    """
    Prefer a hosted URL from the API; otherwise return HTML hint with deposit address + amount.
    """
    for k in ("invoice_url", "pay_url", "payment_url", "redirect_url"):
        v = np.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v, None
    addr = np.get("pay_address")
    amt = np.get("pay_amount")
    cur = (np.get("pay_currency") or "").strip() or "crypto"
    if addr:
        hint = f"Send <b>{amt} {cur}</b> to:\n<code>{addr}</code>"
        return None, hint
    return None, None
