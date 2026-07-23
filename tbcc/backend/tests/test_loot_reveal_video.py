"""Tests for animated loot reveal MP4 mux."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_loot_reveal_video_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TBCC_LOOT_REVEAL_VIDEO", raising=False)
    from app.services.loot_reveal_video import compose_reveal_card_mp4, loot_reveal_video_enabled

    assert loot_reveal_video_enabled() is False
    mp4, note = compose_reveal_card_mp4(b"\xff\xd8\xff" + b"x" * 100)
    assert mp4 is None
    assert note == "disabled"


def test_compose_reveal_card_mp4_no_background(monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_REVEAL_VIDEO", "1")
    from app.services.loot_reveal_video import compose_reveal_card_mp4

    with patch("app.services.loot_reveal_video.pick_background_loop", return_value=None):
        mp4, note = compose_reveal_card_mp4(b"\xff\xd8\xff" + b"x" * 100)
    assert mp4 is None
    assert note == "no_background_loops"


def test_mux_card_on_loop_success(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_REVEAL_VIDEO", "1")
    bg = tmp_path / "loop.mp4"
    bg.write_bytes(b"fake-bg")
    out_mp4 = b"\x00\x00\x00\x18ftypmp42" + b"z" * 5000

    with patch("app.services.loot_reveal_video.ffmpeg_available", return_value=True), patch(
        "app.services.loot_reveal_video.subprocess.run"
    ) as run_mock:

        def _fake_run(cmd, **kwargs):
            out = Path(cmd[-1])
            out.write_bytes(out_mp4)

        run_mock.side_effect = _fake_run
        from app.services.loot_reveal_video import mux_card_on_loop

        data = mux_card_on_loop(b"\xff\xd8\xff" + b"c" * 200, bg, duration_s=2.0, size=256)
    assert data == out_mp4
    assert run_mock.called


def test_build_reveal_card_mp4_wraps_png(monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_REVEAL_VIDEO", "1")
    fake_jpeg = b"\xff\xd8" + b"j" * 500
    fake_mp4 = b"ftyp" + b"m" * 6000

    with patch(
        "app.services.loot_tier_card_assets.build_reveal_card_png",
        return_value=(fake_jpeg, "composite"),
    ), patch(
        "app.services.loot_reveal_video.compose_reveal_card_mp4",
        return_value=(fake_mp4, "mp4 bg=loop.mp4"),
    ):
        from app.services.loot_tier_card_assets import build_reveal_card_mp4

        mp4, note = build_reveal_card_mp4(5, preview={"seed": 42})
    assert mp4 == fake_mp4
    assert "mp4 bg=loop.mp4" in note


def test_reveal_send_animation_when_video_enabled():
    import asyncio
    from unittest.mock import AsyncMock, patch

    from app.services.loot_preview_delivery import _send_loot_preview_to_chat_inner
    from app.services.telegram_message_effects import EFFECT_SPARKLES

    fake_jpeg = b"\xff\xd8" + b"x" * 4000
    fake_mp4 = b"ftyp" + b"v" * 8000
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    bot = AsyncMock()
    preview = {"rarity_tier": 5, "seed": 7, "media": []}
    delivery: dict = {"notes": []}

    async def _run():
        with patch(
            "app.services.loot_preview_delivery.build_reveal_card_png",
            return_value=(fake_jpeg, "composite"),
        ), patch(
            "app.services.loot_preview_delivery._encode_reveal_card_mp4",
            return_value=(fake_mp4, "mp4 bg=loop.mp4"),
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
    assert bot.send_animation.await_count >= 1
    assert bot.send_photo.await_count == 0
    assert any("tier card video:" in n for n in delivery["notes"])
