"""Tests for AOF Gemini promo prompt builder (no API calls)."""

from __future__ import annotations

import pytest

from app.services.gemini_promo_prompt import (
    FORMAT_SPECS,
    build_prompt,
    list_presets,
    resolve_preset,
    scene_text,
)


def test_list_presets_includes_martyrs_ma07_10():
    assert "martyrs-ma07-10" in list_presets()


def test_resolve_preset_martyrs_ma07_10():
    fmt, scenes, style = resolve_preset("martyrs-ma07-10")
    assert fmt == "grid-2x2-9x16"
    assert scenes == ["ma-07", "ma-08", "ma-09", "ma-10"]
    assert "Martyrs" in style


def test_scene_ma07_has_breakfast_label():
    label, text = scene_text("ma-07")
    assert "Breakfast" in label or "Dining" in label
    assert "trench coat" in text.lower() or "trench-coat" in text.lower()


def test_build_grid_prompt_structure():
    prompt, aspect = build_prompt(
        format_key="grid-2x2-9x16",
        scene_ids=["ma-07", "ma-08", "ma-09", "ma-10"],
        style="Test style line.",
    )
    assert aspect == "9:16"
    assert "TOP-LEFT" in prompt
    assert "t.me/aofmainhub" in prompt
    assert "NICHE LANES" in prompt
    assert "ma-07" in prompt.lower() or "MA-07" in prompt
    assert "2×2" in prompt or "2x2" in prompt.lower()


def test_build_single_prompt():
    prompt, aspect = build_prompt(
        format_key="single-9x16",
        scene_ids=["ma-07"],
    )
    assert aspect == "9:16"
    assert "ONE image" in prompt
    assert len(prompt) > 200


def test_format_specs_cover_main_social_formats():
    assert "grid-2x2-9x16" in FORMAT_SPECS
    assert "filmstrip-4x16x9" in FORMAT_SPECS


def test_wrong_scene_count_raises():
    with pytest.raises(ValueError, match="needs"):
        build_prompt(format_key="grid-2x2-9x16", scene_ids=["ma-07"])
