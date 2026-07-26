"""Shared Telegram Bot API transport (httpx) for loot bot, relay, and goblin."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def tg_post_with_token(
    method: str,
    payload: dict[str, Any],
    token: str,
    *,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """POST to api.telegram.org/bot<token>/<method>; returns {ok, result?} or {ok: False, error}."""
    token = (token or "").strip()
    if not token:
        return {"ok": False, "error": "bot_token_unset"}
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, json=payload)
            data = r.json() if r.content else {}
            if r.status_code != 200 or not data.get("ok"):
                return {"ok": False, "error": str(data)[:400], "status": r.status_code}
            return {"ok": True, "result": data.get("result")}
    except Exception as e:
        logger.debug("tg_post_with_token %s failed: %s", method, e)
        return {"ok": False, "error": str(e)[:300]}


def relay_use_bot_api() -> bool:
    """When true, listening relay main body uses Bot API (ops_relay) instead of Telethon poster lock."""
    return (os.getenv("TBCC_RELAY_USE_BOT_API") or "").strip().lower() in ("1", "true", "yes", "on")
