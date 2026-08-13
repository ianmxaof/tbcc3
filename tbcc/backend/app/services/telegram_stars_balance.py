"""Telegram Bot API Stars balance + transactions (reconcile vs TBCC ledger)."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _bot_token() -> str:
    return (
        (os.getenv("BOT_TOKEN") or "").strip()
        or (os.getenv("TBCC_PAYMENT_BOT_TOKEN") or "").strip()
    )


def _api_call(method: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    token = _bot_token()
    if not token:
        return {"ok": False, "error": "BOT_TOKEN / TBCC_PAYMENT_BOT_TOKEN unset"}
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.post(url, json=params or {})
            data = r.json()
    except Exception as e:
        logger.warning("telegram stars API %s failed: %s", method, e)
        return {"ok": False, "error": str(e)[:240]}
    if not isinstance(data, dict):
        return {"ok": False, "error": "non-object response"}
    if not data.get("ok"):
        desc = (data.get("description") or data.get("error") or "telegram error")[:240]
        return {"ok": False, "error": desc, "error_code": data.get("error_code")}
    return {"ok": True, "result": data.get("result")}


def fetch_bot_stars_balance() -> dict[str, Any]:
    """
    GET getMyStarBalance (Bot API 7.4+) — amount of Stars available to the bot.

    Falls back gracefully when the method is unavailable on older bots/API.
    """
    out = _api_call("getMyStarBalance")
    if not out.get("ok"):
        # Older docs / community nodes used getBotStarsBalance — try once.
        alt = _api_call("getBotStarsBalance")
        if alt.get("ok"):
            out = alt
        else:
            return out
    result = out.get("result") or {}
    amount = result.get("amount")
    try:
        stars = int(amount) if amount is not None else None
    except (TypeError, ValueError):
        stars = None
    return {
        "ok": True,
        "amount_stars": stars,
        "raw": result,
    }


def fetch_star_transactions(*, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """GET getStarTransactions — recent bot Stars ledger from Telegram."""
    lim = max(1, min(100, int(limit)))
    off = max(0, int(offset))
    out = _api_call("getStarTransactions", params={"offset": off, "limit": lim})
    if not out.get("ok"):
        return out
    result = out.get("result") or {}
    txs = result.get("transactions") if isinstance(result, dict) else None
    if not isinstance(txs, list):
        txs = []
    return {
        "ok": True,
        "count": len(txs),
        "transactions": txs[:lim],
        "raw": result if isinstance(result, dict) else {},
    }


def telegram_stars_reconcile_snapshot(*, transaction_limit: int = 15) -> dict[str, Any]:
    """Live Telegram Stars view for ops picture (best-effort; never raises)."""
    balance = fetch_bot_stars_balance()
    txs = fetch_star_transactions(limit=transaction_limit)
    sample: list[dict[str, Any]] = []
    if txs.get("ok"):
        for row in txs.get("transactions") or []:
            if not isinstance(row, dict):
                continue
            sample.append(
                {
                    "id": row.get("id"),
                    "amount": (row.get("amount") or {}).get("amount")
                    if isinstance(row.get("amount"), dict)
                    else row.get("amount"),
                    "date": row.get("date"),
                    "source": list((row.get("source") or {}).keys())[:3]
                    if isinstance(row.get("source"), dict)
                    else None,
                }
            )
    return {
        "balance": balance,
        "transactions": {
            "ok": bool(txs.get("ok")),
            "count": int(txs.get("count") or 0),
            "error": txs.get("error"),
            "sample": sample[:10],
        },
        "note": (
            "Telegram Bot API balance/transactions vs TBCC income_entries XTR. "
            "Gaps are normal (companion Stars, refunds, hold window, missing backfill)."
        ),
    }
