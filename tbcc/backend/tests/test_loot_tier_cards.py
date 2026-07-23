"""Tests for loot tier rename + ASCII roll dividers + Gemini loot card prompts."""

from __future__ import annotations

import random

import pytest

from app.services.gemini_loot_card_prompt import (
    FORMAT_SPECS,
    build_prompt,
    build_prompt_for_tier,
    list_presets,
    list_scenes,
    resolve_preset,
    tier_scene_id,
)
from app.services.loot_roll_presentation import (
    ROLL_DIVIDERS,
    build_roll_divider_html,
    pick_tier_flavor,
    wrap_tier_card_body,
)
from app.services.loot_tier_catalog import TIER_META, preview_summary_fields, tier_display_name


def test_ten_tiers_named_filthy_ladder():
    assert len(TIER_META) == 10
    assert TIER_META[1]["name"] == "Crumb"
    assert TIER_META[5]["name"] == "Drip"
    assert TIER_META[10]["name"] == "Godroll"
    assert "Dust" not in {m["name"] for m in TIER_META.values()}
    assert "Ascension" not in {m["name"] for m in TIER_META.values()}


def test_tier_display_includes_world():
    assert "World 1-1" in tier_display_name(1)
    assert "Crumb" in tier_display_name(1)
    assert "Godroll" in tier_display_name(10)


def test_preview_summary_fields():
    s = preview_summary_fields(7)
    assert s["tier_name"] == "Filth"
    assert "Vault" in s["tier_tagline"] or "vault" in s["tier_tagline"].lower() or "Packs" in s["tier_tagline"]


def test_roll_dividers_use_pre_ascii():
    assert len(ROLL_DIVIDERS) >= 3
    for d in ROLL_DIVIDERS:
        assert d.startswith("<pre>")
        assert d.endswith("</pre>")
        assert "<i>" not in d


def test_build_roll_divider_deterministic_seed():
    a = build_roll_divider_html({"seed": 42})
    b = build_roll_divider_html({"seed": 42})
    assert a == b
    assert a.startswith("<pre>")


def test_preparing_and_inventory():
    from app.services.loot_roll_presentation import (
        ROLL_PREPARING_LINES,
        build_preparing_html,
        copy_bank_inventory,
    )

    assert len(ROLL_PREPARING_LINES) >= 8
    html = build_preparing_html({"seed": 7})
    assert html.startswith("<i>")
    inv = copy_bank_inventory()
    assert inv["roll_dividers"] >= 8
    assert inv["preparing_lines"] >= 8
    assert inv["tier_flavor_total"] >= 40


def test_wrap_tier_card_uses_code_frames():
    out = wrap_tier_card_body(10, "<b>hi</b>")
    assert "<code>" in out
    assert "godroll" in out.lower()
    assert "╔" in out
    assert out.count("═") >= 4


def test_build_centered_card_frame():
    from app.services.loot_roll_presentation import build_centered_card_frame

    top, bottom = build_centered_card_frame("drip", width=32)
    assert len(top) == 32
    assert "drip" in top
    assert top.startswith("╔")
    assert bottom.startswith("╚")
    assert "│││" in bottom


def test_classify_frame_style_copper():
    from PIL import Image

    from app.services.loot_card_frame_styles import classify_frame_style

    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    px = im.load()
    for y in range(8):
        for x in range(64):
            px[x, y] = (180, 90, 40, 255)
    assert classify_frame_style(im) == "b"


def test_pick_tier_flavor_from_bank():
    flavor = pick_tier_flavor(10, random.Random(1))
    assert isinstance(flavor, str) and len(flavor) > 8


def test_loot_card_presets_cover_all_tiers():
    scenes = list_scenes()
    for t in range(1, 11):
        assert tier_scene_id(t) in scenes
    assert "tier-10-godroll" in list_presets()


def test_build_loot_card_prompt_for_tier():
    prompt, aspect = build_prompt_for_tier(7)
    assert aspect == "1:1"
    assert "AOF LOOT" in prompt
    assert "FILTH" in prompt
    assert "NO QR" in prompt.upper() or "No QR" in prompt
    assert "nudity" in prompt.lower() or "explicit" in prompt.lower()
    assert "vault" in prompt.lower() or "RESTRICTED" in prompt
    assert "minors" in prompt.lower() or "AVOID" in prompt


def test_build_filmstrip_prompt():
    prompt, aspect = build_prompt(
        format_key="filmstrip-5-cards",
        scene_ids=["tier-01", "tier-03", "tier-05", "tier-07", "tier-10"],
    )
    assert aspect == "9:16"
    assert "FIVE" in prompt or "five" in prompt.lower()
    assert "GODROLL" in prompt


def test_resolve_preset_godroll():
    fmt, scenes, style = resolve_preset("tier-10-godroll")
    assert fmt == "card-1x1"
    assert scenes == ["tier-10"]
    assert "GODROLL" in style.upper() or "godroll" in style.lower() or "Boss" in style


def test_wrong_scene_count_raises():
    with pytest.raises(ValueError, match="needs"):
        build_prompt(format_key="filmstrip-5-cards", scene_ids=["tier-01"])


def test_format_specs_include_card():
    assert "card-1x1" in FORMAT_SPECS
    assert "card-4x5" in FORMAT_SPECS
