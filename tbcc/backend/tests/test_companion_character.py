"""Tests for companion character persistence."""

from __future__ import annotations

from app.services.companion_character import get_character, save_character, set_character_name


def test_character_roundtrip_memory():
    uid = 99001
    char = save_character(user_id=uid, look_summary="breast_size=big, body_type=curvy", pose="Wet girl")
    assert char.name
    loaded = get_character(uid)
    assert loaded is not None
    assert loaded.pose == "Wet girl"
    assert "big" in loaded.look_summary
    renamed = set_character_name(uid, "Mika")
    assert renamed is not None
    assert renamed.name == "Mika"
    assert "first person" in renamed.prompt_block().lower()
