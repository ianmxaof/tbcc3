"""Fire-and-forget outbound webhooks (Discord, Zapier, custom HTTPS)."""
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def notify_discord_webhook_text(webhook_url: str | None, content: str, *, timeout_s: float = 8.0) -> None:
    """POST { \"content\": \"...\" } to a Discord channel webhook (not a discord.gg invite link)."""
    if not webhook_url or not str(webhook_url).strip():
        return
    url = str(webhook_url).strip()
    if "discord.com/api/webhooks" not in url:
        logger.warning("discord webhook skipped (expected discord.com/api/webhooks URL)")
        return
    body = (content or "").strip()
    if not body:
        return
    if len(body) > 2000:
        body = body[:1997] + "…"
    try:
        with httpx.Client(timeout=timeout_s) as client:
            r = client.post(url, json={"content": body})
            if r.status_code >= 400:
                logger.warning("discord webhook returned %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("discord webhook failed: %s", e)


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
