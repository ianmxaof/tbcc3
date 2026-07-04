"""Fire-and-forget outbound webhooks (Discord, Zapier, custom HTTPS)."""
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def notify_discord_webhook_text(
    webhook_url: str | None,
    content: str,
    *,
    timeout_s: float = 8.0,
    thread_name: str | None = None,
) -> bool:
    """POST to a Discord channel webhook (not a discord.gg invite link). Returns True on 2xx."""
    if not webhook_url or not str(webhook_url).strip():
        return False
    url = str(webhook_url).strip()
    if "discord.com/api/webhooks" not in url:
        logger.warning("discord webhook skipped (expected discord.com/api/webhooks URL)")
        return False
    body = (content or "").strip()
    if not body:
        return False
    if len(body) > 2000:
        body = body[:1997] + "…"
    payload: dict[str, Any] = {"content": body}
    tname = (thread_name or os.getenv("TBCC_DISCORD_WEBHOOK_THREAD_NAME") or "").strip()
    if tname:
        payload["thread_name"] = tname[:100]
    try:
        with httpx.Client(timeout=timeout_s) as client:
            r = client.post(url, json=payload)
            if r.status_code >= 400:
                logger.warning("discord webhook returned %s: %s", r.status_code, r.text[:200])
                return False
            return True
    except Exception as e:
        logger.warning("discord webhook failed: %s", e)
        return False


def notify_outbound_webhook(webhook_url: str | None, payload: dict[str, Any], *, timeout_s: float = 5.0) -> None:
    if not webhook_url or not str(webhook_url).strip():
        return
    url = str(webhook_url).strip()
    if not url.startswith("https://") and not url.startswith("http://"):
        logger.warning("outbound webhook ignored (not http/https): %s", url[:80])
        return
    try:
        with httpx.Client(timeout=timeout_s) as client:
            r = client.post(url, json=payload)
            if r.status_code >= 400:
                logger.warning("webhook returned %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("webhook request failed: %s", e)
