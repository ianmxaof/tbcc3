"""User-safe loot delivery error copy — operator details stay in logs only."""

from __future__ import annotations

import html
import logging

logger = logging.getLogger(__name__)


def loot_delivery_failed_user_html(
    *,
    headline: str,
    technical_note: str = "",
) -> str:
    if technical_note:
        logger.warning("loot delivery failed: %s", technical_note[:500])
    return (
        f"<b>{html.escape(headline)}</b>\n"
        "We couldn't deliver a card right now. Tap <b>/roll</b> again in a few seconds."
    )
