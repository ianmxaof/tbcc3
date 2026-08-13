"""Tests for companion body preference helpers."""

from __future__ import annotations

from app.services.companion_body_prefs import load_body_prefs, save_body_pref


def test_body_prefs_roundtrip():
    ud: dict = {}
    save_body_pref(ud, "age", "30")
    save_body_pref(ud, "body_type", "curvy")
    save_body_pref(ud, "breast_size", "big")
    prefs = load_body_prefs(ud)
    assert prefs.age == "30"
    assert prefs.body_type == "curvy"
    assert prefs.breast_size == "big"
    assert prefs.to_api_kwargs() == {"age": "30", "body_type": "curvy", "breast_size": "big"}


def test_legacy_values_map_to_api_enums():
    ud = {"body_prefs": {"breast_size": "large", "butt_size": "large", "age": "25"}}
    prefs = load_body_prefs(ud)
    assert prefs.breast_size == "big"
    assert prefs.butt_size == "big"
    assert prefs.age == "20"
    assert prefs.to_api_kwargs() == {
        "breast_size": "big",
        "butt_size": "big",
        "age": "20",
        "body_type": "curvy",
    }


def test_big_chest_auto_curvy():
    ud: dict = {}
    save_body_pref(ud, "breast_size", "big")
    prefs = load_body_prefs(ud)
    assert prefs.to_api_kwargs() == {"breast_size": "big", "body_type": "curvy"}


def test_bimbo_preset():
    from app.services.companion_body_prefs import apply_body_preset

    ud: dict = {}
    prefs = apply_body_preset(ud, "bimbo")
    api = prefs.to_api_kwargs()
    assert api["breast_size"] == "big"
    assert api["butt_size"] == "big"
    assert api["body_type"] == "curvy"
    assert api["age"] == "20"
    from app.services.companion_body_prefs import option_button_label

    assert option_button_label("breast_size", "big") == "Chest: Bimbo max"
    assert option_button_label("breast_size", "big", selected=True).startswith("✓")
