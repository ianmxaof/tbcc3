"""Tests for template_expand DSL."""

from __future__ import annotations

from app.services.template_expand import expand_template_tokens


def test_date_token_expansion():
    out = expand_template_tokens("drop {date:%Y} — {weekday}", for_x=True)
    assert len(out) > 10
    assert "drop " in out


def test_prompt_teaser_x_safe():
    out = expand_template_tokens("{prompt_teaser:jackal_tapes_interview}", for_x=True)
    assert "linkvertise" not in out.lower()
    assert "@aofmainhub" in out
