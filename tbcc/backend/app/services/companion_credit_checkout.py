"""Deep links from companion bot → payment bot credit pack catalog."""

from __future__ import annotations

from typing import Any

from app.data.companion_credit_packs import COMPANION_CREDIT_PACKS
from app.services.aof_social_links import payment_bot_username


def companion_credit_catalog_start_url(*, sku: str | None = None) -> str:
    un = payment_bot_username()
    if not un:
        return ""
    payload = "companion"
    if sku:
        pack_sku = sku if sku.startswith("companion_") else f"companion_{sku}"
        payload = pack_sku
    return f"https://t.me/{un}?start={payload}"


def companion_credit_pack_button_rows() -> list[list[dict[str, str]]]:
    """Inline keyboard rows: one URL button per pack + full catalog."""
    rows: list[list[dict[str, str]]] = []
    for pack in COMPANION_CREDIT_PACKS:
        url = companion_credit_catalog_start_url(sku=pack.sku)
        if not url:
            continue
        rows.append(
            [
                {
                    "text": f"📦 {pack.credit_units} reveals — {pack.price_stars}⭐",
                    "url": url,
                }
            ]
        )
    catalog = companion_credit_catalog_start_url()
    if catalog:
        rows.append([{"text": "💳 All packs (Stars + crypto)", "url": catalog}])
    return rows


def companion_credit_pack_inline_keyboard_rows() -> list[list[dict[str, str]]]:
    return companion_credit_pack_button_rows()


def companion_return_to_companion_url() -> str:
    from app.services.aof_social_links import companion_bot_username

    un = companion_bot_username()
    return f"https://t.me/{un}" if un else ""
