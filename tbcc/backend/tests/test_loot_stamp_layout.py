from app.services.loot_tier_card_assets import (
    _badge_plate_lines,
    _world_badge_lines,
    _world_coord_compact,
)


def test_world_coord_compact():
    assert _world_coord_compact("World 4-1") == "4-1"
    assert _world_coord_compact("world 2-1") == "2-1"
    assert _world_coord_compact("3-1") == "3-1"
    assert _world_coord_compact("") == ""


def test_world_badge_lines_splits_world_coordinate():
    assert _world_badge_lines("World 2-1") == ("World", "2  -  1")
    assert _world_badge_lines("world 3-1") == ("World", "3  -  1")


def test_badge_plate_lines_stacked():
    assert _badge_plate_lines(4, "World 2-1") == ["TIER 4", "World", "2  -  1"]
