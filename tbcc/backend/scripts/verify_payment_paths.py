"""
Smoke-test payment paths without spending money (API + logic + NOWPayments invoice create).

Run from tbcc/backend:
  py -3.13 scripts/verify_payment_paths.py
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parents[1]
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()


def _ok(label: str) -> None:
    print(f"  OK  {label}")


def _fail(label: str, detail: str = "") -> None:
    print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))


def main() -> int:
    import httpx
    from bots.payment_pipeline import parse_invoice_payload, validate_pre_checkout
    from app.database.session import SessionLocal
    from app.models.subscription_plan import SubscriptionPlan
    from app.services.nowpayments_client import (
        crypto_auto_checkout_ready,
        plan_crypto_checkout_eligible,
        plan_nowpayments_usd_quote,
        public_api_base_url,
        use_invoice_checkout,
        verify_ipn_signature,
    )

    print("TBCC payment path verification (no real Stars/crypto spend)\n")
    fails = 0

    # --- config ---
    print("[config]")
    if crypto_auto_checkout_ready():
        _ok("crypto_auto_checkout")
    else:
        _fail("crypto_auto_checkout", "check NOWPayments keys + TBCC_PUBLIC_API_BASE_URL")
        fails += 1
    if use_invoice_checkout():
        _ok("invoice checkout (any coin picker)")
    else:
        _fail("invoice checkout disabled", "set TBCC_NOWPAYMENTS_USE_INVOICE=1")
        fails += 1
    pub = public_api_base_url()
    if pub:
        _ok(f"public_api_base_url configured ({pub[:40]}…)")
    else:
        _fail("TBCC_PUBLIC_API_BASE_URL missing")
        fails += 1

    api_base = (os.getenv("TBCC_API_URL") or "http://localhost:8000").strip().rstrip("/")
    try:
        r = httpx.get(f"{api_base}/health", timeout=15)
        if r.status_code == 200:
            _ok(f"API /health ({api_base[:40]}…)")
        else:
            _fail("API /health", str(r.status_code))
            fails += 1
    except Exception as e:
        _fail("API /health", str(e))
        fails += 1

    # --- Stars pre_checkout logic ---
    print("\n[Stars pipeline logic]")
    db = SessionLocal()
    try:
        plans = db.query(SubscriptionPlan).filter(SubscriptionPlan.is_active.is_(True)).all()
        for p in plans[:6]:
            payload = f"sub_{p.id}_999888777"
            parsed = parse_invoice_payload(payload)
            if not parsed:
                _fail(f"parse payload plan {p.id}")
                fails += 1
                continue
            q = plan_nowpayments_usd_quote(
                price_stars=int(p.price_stars or 0),
                nowpayments_price_usd=float(p.nowpayments_price_usd) if p.nowpayments_price_usd else None,
            )
            section = "loot" if "loot" in (p.name or "").lower() else "main"
            crypto_ok = plan_crypto_checkout_eligible(
                price_stars=int(p.price_stars or 0),
                nowpayments_price_usd=float(p.nowpayments_price_usd) if p.nowpayments_price_usd else None,
                bot_section=section,
            )
            print(
                f"  plan {p.id}: {p.price_stars} stars catalog ${q['catalog_usd']} "
                f"billed ${q['billed_usd']} crypto={'yes' if crypto_ok else 'no'}"
            )
        _ok("invoice payload parse + plan quotes")
    finally:
        db.close()

    class _FakeQuery:
        invoice_payload = "sub_6_999888777"
        currency = "XTR"
        total_amount = 500

        class from_user:
            id = 999888777

    async def _fake_plan(_pid: int):
        return {"id": 10, "is_active": True, "product_type": "subscription", "price_stars": 500}

    ok, err = asyncio.run(validate_pre_checkout(_FakeQuery(), _fake_plan))
    if ok:
        _ok("pre_checkout validation (AOF VIP 1 Month 500 stars)")
    else:
        _fail("pre_checkout", err or "")
        fails += 1

    # --- IPN signature ---
    print("\n[Crypto IPN]")
    secret = (os.getenv("TBCC_NOWPAYMENTS_IPN_SECRET") or "").strip()
    body = {"payment_status": "finished", "order_id": "EPO-VERIFY", "payment_id": 1}
    sig = hmac.new(
        secret.encode(),
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode(),
        hashlib.sha512,
    ).hexdigest()
    if secret and verify_ipn_signature(body, sig, secret):
        _ok("IPN HMAC signature verify")
    else:
        _fail("IPN signature")
        fails += 1

    # --- Live invoice create (creates NP invoice, no payment) ---
    print("\n[NOWPayments invoice create — no payment required]")
    key = os.getenv("TBCC_INTERNAL_API_KEY", "")
    base = (os.getenv("TBCC_API_URL") or "http://127.0.0.1:8000").rstrip("/")
    for plan_id, label in [(10, "AOF VIP 1 Month"), (2, "Loot 150 stars")]:
        try:
            r = httpx.post(
                f"{base}/external-payment-orders/",
                json={"telegram_user_id": 999888777, "plan_id": plan_id},
                headers={"X-TBCC-Internal-Key": key},
                timeout=45,
            )
            if r.status_code != 200:
                _fail(f"order {label}", r.text[:120])
                fails += 1
                continue
            d = r.json()
            url = d.get("crypto_pay_url") or ""
            if url.startswith("http"):
                _ok(f"{label} invoice URL ({url[:50]}...)")
            else:
                _fail(f"{label} invoice URL missing", (d.get("crypto_checkout_error") or "")[:80])
                fails += 1
        except Exception as e:
            _fail(f"order {label}", str(e))
            fails += 1

    print("\n" + ("All automated checks passed." if fails == 0 else f"{fails} check(s) failed."))
    print(
        "\nNote: Real Telegram Stars and on-chain crypto still need a live buyer payment — "
        "this script does not guarantee that, only that TBCC + NOWPayments wiring is healthy."
    )
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
