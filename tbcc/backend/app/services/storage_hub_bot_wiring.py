"""Which bot owns Storage Hub operator duties (panels, /deposit, Q&A controls)."""

from __future__ import annotations

import os


def payment_storage_hub_enabled() -> bool:
    return (os.getenv("TBCC_PAYMENT_STORAGE_HUB") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def album_composer_storage_hub_enabled() -> bool:
    raw = (os.getenv("TBCC_ALBUM_COMPOSER_STORAGE_HUB") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    if payment_storage_hub_enabled():
        return False
    from bots.storage_hub_deposit_bot import album_composer_storage_deposit_enabled

    return album_composer_storage_deposit_enabled()


def gatekeeper_review_bot_default() -> str:
    raw = (os.getenv("TBCC_GATEKEEPER_REVIEW_BOT") or "").strip().lower()
    if raw:
        return raw
    return "payment" if payment_storage_hub_enabled() else "album_composer"
