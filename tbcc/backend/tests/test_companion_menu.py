"""Tests for companion menu helpers."""

from __future__ import annotations

from app.services.companion_body_prefs import apply_body_preset
from app.services.companion_menu import (
    VIDEO_POSES_PER_PAGE,
    body_preset_keyboard,
    main_menu_keyboard,
    pose_keyboard,
    video_pose_keyboard,
    video_pose_page_count,
)


def test_main_menu_has_video_button():
    kb = main_menu_keyboard(age_confirmed=True, video_enabled=True)
    flat = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "comp_menu:video" in flat
    assert "comp_menu:styles" in flat


def test_pose_keyboard_marks_selected():
    kb = pose_keyboard(["Doggy Style", "Wet girl"], selected="Wet girl")
    assert kb is not None
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any(t.startswith("✓") and "Wet girl" in t for t in labels)
    flat = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "comp_menu:home" in flat


def test_pose_keyboard_three_columns():
    poses = [f"Pose{i}" for i in range(7)]
    kb = pose_keyboard(poses)
    assert kb is not None
    # First two rows should be full 3-wide.
    assert len(kb.inline_keyboard[0]) == 3
    assert len(kb.inline_keyboard[1]) == 3
    assert kb.inline_keyboard[-1][1].callback_data == "comp_menu:home"


def test_body_preset_keyboard():
    ud: dict = {}
    apply_body_preset(ud, "curvy")
    kb = body_preset_keyboard(ud)
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("Curvy" in t and t.startswith("✓") for t in labels)
    flat = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "comp_menu:home" in flat


def test_delivery_navigation_has_main_menu(monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_BOT_USERNAME", "aof_lootgod_bot")
    monkeypatch.setenv("TBCC_PAYMENT_BOT_USERNAME", "aofsubscriptions_bot")
    from app.services.companion_menu import delivery_navigation_keyboard

    kb = delivery_navigation_keyboard(video_enabled=True)
    flat_cb = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
    flat_url = [btn.url for row in kb.inline_keyboard for btn in row if btn.url]
    assert "comp_menu:home" in flat_cb
    assert "comp_menu:redo" in flat_cb
    assert "comp_menu:reveal" in flat_cb
    assert "comp_menu:poses" in flat_cb
    assert any("loot_free" in u for u in flat_url)
    assert any("subscribe" in u for u in flat_url)


def test_apply_natural_preset_api_kwargs():
    ud: dict = {}
    prefs = apply_body_preset(ud, "natural")
    assert prefs.to_api_kwargs()["body_type"] == "normal"


def test_video_pose_keyboard_paginates():
    poses = [{"id": f"id{i}", "name": f"Pose {i}"} for i in range(20)]
    kb = video_pose_keyboard(poses, page=0)
    assert kb is not None
    pose_buttons = [
        btn
        for row in kb.inline_keyboard
        for btn in row
        if btn.callback_data
        and btn.callback_data.startswith("comp_vpose:")
        and btn.callback_data != "comp_vpose:clear"
    ]
    assert len(pose_buttons) == VIDEO_POSES_PER_PAGE
    assert video_pose_page_count(poses) == 2
    page2 = video_pose_keyboard(poses, page=1)
    assert page2 is not None
    nav = [btn.callback_data for row in page2.inline_keyboard for btn in row if btn.callback_data]
    assert "comp_vpage:0" in nav
