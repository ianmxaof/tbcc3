"""Tests for /model creator recruitment post builders."""

from app.services.loot_creator_recruitment_posts import (
    ALL_VARIANTS,
    build_creator_recruitment_html,
    build_x_recruitment_line,
    pick_variant_for_day,
)


def test_all_variants_build_html():
    for v in ALL_VARIANTS:
        html = build_creator_recruitment_html(variant=v)
        assert "/model" in html
        assert len(html) > 80


def test_pick_variant_stable():
    from datetime import datetime, timezone

    dt = datetime(2026, 8, 1, tzinfo=timezone.utc)
    assert pick_variant_for_day(day=dt) == pick_variant_for_day(day=dt)


def test_x_line_short():
    line = build_x_recruitment_line(variant="G")
    assert "aof_lootgod_bot" in line
    assert "/model" in line
    assert len(line) < 280
