"""Tests for companion pose filtering."""

from __future__ import annotations

from app.services.companion_poses import BLOCKED_PHOTO_POSES, filter_photo_poses


def test_lingerie_blocked():
    poses = ["Cumshot", "Lingerie", "Wet girl"]
    out = filter_photo_poses(poses)
    assert "Lingerie" not in out
    assert "Cumshot" in out
    assert "Lingerie" in BLOCKED_PHOTO_POSES
