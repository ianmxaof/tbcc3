"""Loot reveal delivery: card photo + message effects."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.telegram_message_effects import EFFECT_SPARKLES


def test_reveal_send_photo_passes_message_effect_id():
    from app.services.loot_preview_delivery import _send_loot_preview_to_chat_inner

    fake_jpeg = b"\xff\xd8" + b"x" * 4000
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    bot = AsyncMock()
    preview = {
        "rarity_tier": 5,
        "world_label": "World 2-2",
        "tier_name": "drip",
        "tagline": "Mid-heat.",
        "seed": 1,
        "media": [],
    }
    delivery: dict = {"notes": []}

    async def _run():
        with patch(
            "app.services.loot_preview_delivery.build_reveal_card_png",
            return_value=(fake_jpeg, "composite pool=blank frames=18"),
        ), patch(
            "app.services.loot_preview_delivery.loot_roll_effect_id",
            return_value=EFFECT_SPARKLES,
        ), patch(
            "app.services.loot_preview_delivery.build_tier_opening_html",
            return_value="<b>drip</b>",
        ), patch(
            "app.services.loot_preview_delivery.build_roll_divider_html",
            return_value="<pre>x</pre>",
        ), patch(
            "app.services.loot_preview_delivery.build_tier_flavor_html",
            return_value="",
        ), patch(
            "app.services.loot_preview_delivery.build_preparing_html",
            return_value="<i>wait</i>",
        ):
            await _send_loot_preview_to_chat_inner(
                db,
                bot=bot,
                chat_id=12345,
                preview=preview,
                spoiler_default=False,
                include_affiliate_footer=False,
                delivery=delivery,
            )

    asyncio.run(_run())

    assert bot.send_photo.await_count >= 1
    first_kwargs = bot.send_photo.await_args_list[0].kwargs
    assert first_kwargs.get("message_effect_id") == EFFECT_SPARKLES


def test_reveal_send_photo_falls_back_when_effect_rejected():
    from telegram.error import TelegramError

    from app.services.loot_preview_delivery import _send_loot_preview_to_chat_inner

    fake_jpeg = b"\xff\xd8" + b"y" * 4000
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    bot = AsyncMock()
    bot.send_photo.side_effect = [
        TelegramError("Premium_account_required"),
        TelegramError("Premium_account_required"),
        MagicMock(),
    ]
    preview = {"rarity_tier": 3, "seed": 2, "media": []}
    delivery: dict = {"notes": []}

    async def _run():
        with patch(
            "app.services.loot_preview_delivery.build_reveal_card_png",
            return_value=(fake_jpeg, "composite"),
        ), patch(
            "app.services.loot_preview_delivery.loot_roll_effect_id",
            return_value=EFFECT_SPARKLES,
        ), patch(
            "app.services.loot_preview_delivery.build_tier_opening_html",
            return_value="<b>peek</b>",
        ), patch(
            "app.services.loot_preview_delivery.build_roll_divider_html",
            return_value="<pre>x</pre>",
        ), patch(
            "app.services.loot_preview_delivery.build_tier_flavor_html",
            return_value="",
        ), patch(
            "app.services.loot_preview_delivery.build_preparing_html",
            return_value="<i>wait</i>",
        ):
            await _send_loot_preview_to_chat_inner(
                db,
                bot=bot,
                chat_id=99,
                preview=preview,
                spoiler_default=False,
                include_affiliate_footer=False,
                delivery=delivery,
            )

    asyncio.run(_run())

    assert bot.send_photo.await_count == 3
    last_kwargs = bot.send_photo.await_args_list[2].kwargs
    assert last_kwargs.get("message_effect_id") is None
