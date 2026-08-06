"""Tests for companion menu helpers."""

from __future__ import annotations

from app.services.companion_body_prefs import apply_body_preset
from app.services.companion_menu import body_preset_keyboard, main_menu_keyboard, pose_keyboard


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


def test_body_preset_keyboard():
    ud: dict = {}
    apply_body_preset(ud, "curvy")
    kb = body_preset_keyboard(ud)
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("Curvy" in t and t.startswith("✓") for t in labels)


def test_delivery_navigation_has_main_menu():
    from app.services.companion_menu import delivery_navigation_keyboard

    kb = delivery_navigation_keyboard(video_enabled=True)
    flat = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "comp_menu:home" in flat
    assert "comp_menu:reveal" in flat
    assert "comp_menu:poses" in flat


def test_apply_natural_preset_api_kwargs():
    ud: dict = {}
    prefs = apply_body_preset(ud, "natural")
    assert prefs.to_api_kwargs()["body_type"] == "normal"
