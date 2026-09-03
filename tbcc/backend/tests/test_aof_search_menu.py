"""AOF search lane-picker button tree — /find, /searchmenu, continuation UX."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def test_lane_catalog_excludes_webcams():
    from bots.aof_search_telegram import _lane_catalog

    lanes = _lane_catalog()
    assert "webcams" not in lanes
    assert "milf" in lanes
    assert "goon" in lanes
    assert "packs" in lanes


def test_lane_menu_keyboard_structure():
    from bots.aof_search_telegram import _lane_catalog, lane_menu_keyboard

    kb = lane_menu_keyboard()
    buttons = [b for row in kb.inline_keyboard for b in row]
    assert len(buttons) == len(_lane_catalog())
    assert all(b.callback_data.startswith("find:lane:") for b in buttons)
    assert all(len(row) <= 3 for row in kb.inline_keyboard)
    # every callback_data round-trips to a real lane key
    lane_keys = {b.callback_data.split(":", 2)[-1] for b in buttons}
    assert lane_keys == set(_lane_catalog())


def test_lane_picked_keyboard_has_browse_and_back():
    from bots.aof_search_telegram import _lane_picked_keyboard

    kb = _lane_picked_keyboard("milf")
    flat = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "find:browse:milf" in flat
    assert "find:menu" in flat


def test_build_find_handlers_callback_patterns_cover_menu_lane_browse_more():
    from bots.aof_search_telegram import build_find_handlers

    handlers = build_find_handlers(bot_kind="macro")
    patterns = {
        getattr(h, "pattern").pattern
        for h in handlers
        if getattr(h, "pattern", None) is not None
    }
    assert any(p.startswith("^find:more:") for p in patterns)
    assert any(p.startswith("^find:lane:") for p in patterns)
    assert any(p.startswith("^find:browse:") for p in patterns)
    assert any(p == "^find:menu$" for p in patterns)


def test_consume_find_pending_lane_text_noop_when_nothing_pending():
    from bots.aof_search_telegram import consume_find_pending_lane_text

    context = SimpleNamespace(user_data={})
    update = SimpleNamespace(effective_message=SimpleNamespace(text="hello"))
    handled = asyncio.run(consume_find_pending_lane_text(update, context, bot_kind="macro"))
    assert handled is False
    assert context.user_data == {}


def test_consume_find_pending_lane_text_dispatches_and_clears():
    from bots.aof_search_telegram import _PENDING_LANE_KEY, consume_find_pending_lane_text

    context = SimpleNamespace(user_data={_PENDING_LANE_KEY: "milf"})
    update = SimpleNamespace(effective_message=SimpleNamespace(text="office thick"))

    with patch("bots.aof_search_telegram.cmd_find", new_callable=AsyncMock) as cmd_find:
        handled = asyncio.run(consume_find_pending_lane_text(update, context, bot_kind="macro"))

    assert handled is True
    assert _PENDING_LANE_KEY not in context.user_data
    cmd_find.assert_awaited_once()
    _, kwargs = cmd_find.call_args
    assert kwargs["bot_kind"] == "macro"
    assert "office thick" in kwargs["override_query"]
    assert "🧜‍♀️" in kwargs["override_query"]  # milf emoji prefix
