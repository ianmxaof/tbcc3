"""Tests for companion UI assets."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from app.services.companion_assets import (
    POSE_ALBUM_PRIMARY_COUNT,
    POSE_TELEGRAM_TILE_PX,
    labeled_pose_tile_bytes,
    split_pose_album_batches,
)
from app.services.companion_poses import POSE_SOURCE_FILES


def test_labeled_pose_tile_is_square_512():
    pose = next(iter(POSE_SOURCE_FILES))
    raw = labeled_pose_tile_bytes(pose)
    assert raw
    im = Image.open(BytesIO(raw))
    assert im.size == (POSE_TELEGRAM_TILE_PX, POSE_TELEGRAM_TILE_PX)


def test_split_pose_album_batches_primary_then_overflow():
    poses = list(POSE_SOURCE_FILES.keys())
    batches = split_pose_album_batches(poses)
    assert len(batches) == 2
    assert len(batches[0]) == POSE_ALBUM_PRIMARY_COUNT
    assert len(batches[1]) == len(poses) - POSE_ALBUM_PRIMARY_COUNT


def test_split_pose_album_batches_small_list():
    poses = ["Cumshot", "Blowjob"]
    assert split_pose_album_batches(poses) == [poses]
