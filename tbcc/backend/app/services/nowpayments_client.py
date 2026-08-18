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
    """HTTPS base for IPN callbacks (no trailing slash; must not include /webhooks/...)."""
    u = (os.getenv("TBCC_PUBLIC_API_BASE_URL") or os.getenv("TBCC_PROMO_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    suffix = "/webhooks/nowpayments"
    if u.lower().endswith(suffix):
        u = u[: -len(suffix)].rstrip("/")
        logger.warning(
            "TBCC_PUBLIC_API_BASE_URL must be the API root only (e.g. https://host.ngrok.app); "
            "stripped %s suffix",
            suffix,
        )
    return u


def get_min_checkout_usd() -> float:
    try:
        v = float((os.getenv("TBCC_NOWPAYMENTS_MIN_CHECKOUT_USD") or "0").strip() or "0")
    except Exception:
        v = 0.0
    return max(0.0, v)


def plan_nowpayments_usd_quote(
    *,
    price_stars: int,
    nowpayments_price_usd: float | None = None,
) -> dict[str, float | None]:
    """Catalog USD (Stars/override) vs amount sent to NOWPayments (after min floor)."""
    catalog = (
        float(nowpayments_price_usd)
        if nowpayments_price_usd is not None and float(nowpayments_price_usd) > 0
        else stars_to_usd(int(price_stars or 0))
    )
    min_usd = get_min_checkout_usd()
    billed = max(catalog, min_usd) if min_usd > 0 else catalog
    return {
        "catalog_usd": round(catalog, 2),
        "billed_usd": round(billed, 2),
        "min_checkout_usd": round(min_usd, 2) if min_usd > 0 else None,
    }


def plan_usd_price_label(*, price_stars: int, nowpayments_price_usd: float | None = None) -> str:
    """Formatted "$18" / "$9.60" checkout-button price hint (billed USD, catalog or NOWPayments-floor adjusted)."""
    quote = plan_nowpayments_usd_quote(price_stars=price_stars, nowpayments_price_usd=nowpayments_price_usd)
    billed = float(quote.get("billed_usd") or 0)
    return f"${billed:.0f}" if billed >= 10 else f"${billed:.2f}"


def plan_crypto_checkout_eligible(
    *,
    price_stars: int,
    nowpayments_price_usd: float | None = None,
    bot_section: str | None = None,
) -> bool:
    """
    Loot tiers: Stars-only when fixed-currency deposit would overcharge (legacy).
    With invoice checkout, loot can use crypto at catalog USD (~$2–6).
    """
    section = (bot_section or "main").strip().lower()
    quote = plan_nowpayments_usd_quote(
        price_stars=price_stars,
        nowpayments_price_usd=nowpayments_price_usd,
    )
    catalog = float(quote["catalog_usd"] or 0)
    if catalog <= 0:
        return False
    if section == "loot" and not use_invoice_checkout():
        return False
    return True


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


def crypto_auto_checkout_ready() -> bool:
    """
    True when wallet/crypto orders can get a NOWPayments URL and IPN can auto-fulfill
    (no dashboard mark-paid). Requires public HTTPS API base + API key + IPN secret.
    """
    return bool(
        nowpayments_configured()
        and can_use_nowpayments_ipn()
        and (os.getenv("TBCC_NOWPAYMENTS_IPN_SECRET") or "").strip()
    )


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


def use_invoice_checkout() -> bool:
    """Hosted NOWPayments page where buyer picks any supported coin (recommended)."""
    raw = (os.getenv("TBCC_NOWPAYMENTS_USE_INVOICE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def create_invoice(
    *,
    order_id: str,
    price_usd: float,
    order_description: str,
    ipn_callback_url: str,
    pay_currency: str | None = None,
) -> dict[str, Any]:
    """
    POST /v1/invoice — buyer chooses crypto on hosted page (pay_currency optional).
    """
    key = (os.getenv("TBCC_NOWPAYMENTS_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("TBCC_NOWPAYMENTS_API_KEY not set")

    payload: dict[str, Any] = {
        "price_amount": price_usd,
        "price_currency": "usd",
        "ipn_callback_url": ipn_callback_url,
        "order_id": order_id,
        "order_description": (order_description or "TBCC order")[:512],
    }
    currency = (pay_currency or "").strip()
    if currency:
        payload["pay_currency"] = currency
    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                f"{NP_API}/invoice",
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
        logger.warning("NOWPayments create invoice failed: %s %s", e.response.status_code, detail)
        msg = f"NOWPayments error {e.response.status_code}"
        if detail:
            msg += f": {detail}"
        raise RuntimeError(msg) from e


def create_payment(
    *,
    order_id: str,
    price_usd: float,
    order_description: str,
    ipn_callback_url: str,
    pay_currency: str | None = None,
) -> dict[str, Any]:
    """
    POST /v1/payment — returns API JSON (includes invoice_url or payment id + pay_address).
    """
    key = (os.getenv("TBCC_NOWPAYMENTS_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("TBCC_NOWPAYMENTS_API_KEY not set")

    # If unset, omit pay_currency so hosted checkout can expose more currency choices.
    currency = (pay_currency or os.getenv("TBCC_NOWPAYMENTS_PAY_CURRENCY") or "").strip()
    payload = {
        "price_amount": price_usd,
        "price_currency": "usd",
        "ipn_callback_url": ipn_callback_url,
        "order_id": order_id,
        "order_description": (order_description or "TBCC order")[:512],
    }
    if currency:
        payload["pay_currency"] = currency
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
        msg = f"NOWPayments error {e.response.status_code}"
        if detail:
            msg += f": {detail}"
        raise RuntimeError(msg) from e


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
    # Invoice API nests URL under id sometimes
    iid = np.get("id") or np.get("invoice_id")
    if iid is not None:
        return f"https://nowpayments.io/payment/?iid={iid}", None
    addr = np.get("pay_address")
    amt = np.get("pay_amount")
    cur = (np.get("pay_currency") or "").strip() or "crypto"
    if addr:
        hint = f"Send <b>{amt} {cur}</b> to:\n<code>{addr}</code>"
        return None, hint
    return None, None
