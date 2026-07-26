"""Composite loot reveal cards from frames + band centers."""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image

from app.services.loot_tier_card_assets import (
    build_reveal_card_png,
    center_band_for_tier,
    compose_reveal_card,
    list_center_paths,
    list_frame_paths,
    resolve_tier_card_path,
)
from app.services.telegram_message_effects import (
    DEFAULT_LOOT_ROLL_EFFECT_ID,
    EFFECT_SPARKLES,
    LOOT_ROLL_EFFECT_POOL,
    loot_roll_effect_id,
)


def _make_frame(path: Path, size: int = 256) -> None:
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for y in range(size):
        for x in range(size):
            in_outer = 8 <= x < size - 8 and 8 <= y < size - 8
            in_window = 40 <= x < size - 40 and 40 <= y < size - 40
            if in_outer and not in_window:
                im.putpixel((x, y), (40, 40, 45, 255))
    im.save(path)


def _make_center(path: Path, color: tuple[int, int, int], size: int = 128) -> None:
    Image.new("RGB", (size, size), color).save(path)


def test_center_band_for_tier():
    assert center_band_for_tier(1) == "low"
    assert center_band_for_tier(5) == "low"
    assert center_band_for_tier(6) == "high"
    assert center_band_for_tier(9) == "high"
    assert center_band_for_tier(10) == "godroll"


def test_resolve_tier_card_path_finds_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_TIER_CARD_DIR", str(tmp_path))
    assert resolve_tier_card_path(7) is None
    (tmp_path / "tier-7.png").write_bytes(b"fake-png")
    path = resolve_tier_card_path(7)
    assert path is not None
    assert path.name == "tier-7.png"


def test_sanitize_frame_punches_baked_checker(tmp_path: Path, monkeypatch):
    from app.services.loot_tier_card_assets import sanitize_frame_alpha

    size = 128
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # opaque chrome ring
    for y in range(size):
        for x in range(size):
            in_chrome = 16 <= x < size - 16 and 16 <= y < size - 16
            in_window = 40 <= x < size - 40 and 40 <= y < size - 40
            if in_chrome and not in_window:
                im.putpixel((x, y), (40, 40, 50, 255))
            elif in_window:
                # baked Photoshop checker (opaque greys)
                cell = ((x // 8) + (y // 8)) % 2
                g = 200 if cell else 120
                im.putpixel((x, y), (g, g, g, 255))
    out = sanitize_frame_alpha(im)
    assert out.getpixel((size // 2, size // 2))[3] == 0
    assert out.getpixel((20, 20))[3] > 200


def test_compose_reveal_card_uses_band_center(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_TIER_CARD_DIR", str(tmp_path))
    frames = tmp_path / "frames"
    centers = tmp_path / "centers" / "low"
    frames.mkdir(parents=True)
    centers.mkdir(parents=True)
    _make_frame(frames / "frame-001.png")
    _make_center(centers / "a.jpg", (220, 40, 80))

    data = compose_reveal_card(3, rng=random.Random(1), size=256, stamp_chrome=False)
    assert data is not None
    assert data[:2] == b"\xff\xd8"  # JPEG
    out = Image.open(__import__("io").BytesIO(data))
    assert out.mode == "RGB"
    # Cropped to chrome — should be smaller than full canvas but still filled
    assert out.size[0] <= 256 and out.size[1] <= 256
    assert out.size[0] >= 64 and out.size[1] >= 64
    pix = out.getpixel((out.size[0] // 2, out.size[1] // 2))
    assert pix[0] > 150


def test_compose_crops_exterior_void(tmp_path: Path, monkeypatch):
    """Exterior transparent margins must be trimmed off the final JPEG."""
    monkeypatch.setenv("TBCC_LOOT_TIER_CARD_DIR", str(tmp_path))
    frames = tmp_path / "frames"
    centers = tmp_path / "centers" / "low"
    frames.mkdir(parents=True)
    centers.mkdir(parents=True)
    size = 256
    # Frame chrome inset from canvas edges (transparent exterior)
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for y in range(size):
        for x in range(size):
            in_chrome = 40 <= x < size - 40 and 40 <= y < size - 40
            in_window = 70 <= x < size - 70 and 70 <= y < size - 70
            if in_chrome and not in_window:
                im.putpixel((x, y), (30, 30, 40, 255))
    im.save(frames / "frame-001.png")
    _make_center(centers / "a.jpg", (200, 20, 20))
    data = compose_reveal_card(2, rng=random.Random(0), size=size, stamp_chrome=False)
    out = Image.open(__import__("io").BytesIO(data))
    assert out.size[0] < size - 60
    assert out.size[1] < size - 60
    # corners of cropped card should be chrome-ish / dark, not mid-grey checker
    c = out.getpixel((2, 2))
    assert not (90 <= c[0] <= 210 and abs(c[0] - c[1]) < 20 and abs(c[1] - c[2]) < 20)


def test_window_bbox_ignores_exterior_punch(tmp_path: Path, monkeypatch):
    """Frames punched outside chrome must still yield an interior window."""
    from app.services.loot_tier_card_assets import _window_bbox

    monkeypatch.setenv("TBCC_LOOT_TIER_CARD_DIR", str(tmp_path))
    size = 256
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))  # exterior transparent
    for y in range(size):
        for x in range(size):
            in_chrome = 24 <= x < size - 24 and 24 <= y < size - 24
            in_window = 56 <= x < size - 56 and 56 <= y < size - 56
            if in_chrome and not in_window:
                im.putpixel((x, y), (80, 20, 120, 255))
    x0, y0, x1, y1 = _window_bbox(im)
    assert x0 >= 40 and y0 >= 40
    assert x1 <= size - 40 and y1 <= size - 40
    assert (x1 - x0) > 80 and (y1 - y0) > 80


def test_list_center_paths_skips_migrated_when_real_exists(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_TIER_CARD_DIR", str(tmp_path))
    band = tmp_path / "centers" / "low"
    band.mkdir(parents=True)
    # tiny migrated seed
    Image.new("RGB", (32, 32), (1, 1, 1)).save(band / "migrated-t1-_seed-from-tier-1.png")
    # real still
    Image.new("RGB", (512, 512), (200, 50, 50)).save(band / "ai-001.jpg", quality=90)
    paths = list_center_paths(3)
    assert len(paths) == 1
    assert paths[0].name == "ai-001.jpg"


def test_list_center_paths_band_then_legacy(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_TIER_CARD_DIR", str(tmp_path))
    (tmp_path / "centers" / "t7").mkdir(parents=True)
    _make_center(tmp_path / "centers" / "t7" / "legacy.png", (10, 20, 30))
    assert len(list_center_paths(7)) == 1
    (tmp_path / "centers" / "high").mkdir(parents=True)
    _make_center(tmp_path / "centers" / "high" / "band.png", (200, 10, 10))
    paths = list_center_paths(7)
    assert any(p.name == "band.png" for p in paths)


def test_build_reveal_falls_back_to_static(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_TIER_CARD_DIR", str(tmp_path))
    (tmp_path / "frames").mkdir()
    img = Image.new("RGB", (32, 32), (10, 20, 30))
    img.save(tmp_path / "tier-2.png")
    data, note = build_reveal_card_png(2, rng=random.Random(0))
    assert data is not None
    assert note.startswith("static:")


def test_list_helpers(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_TIER_CARD_DIR", str(tmp_path))
    (tmp_path / "frames").mkdir()
    _make_frame(tmp_path / "frames" / "frame-001.png")
    (tmp_path / "centers" / "low").mkdir(parents=True)
    _make_center(tmp_path / "centers" / "low" / "c.png", (1, 2, 3))
    assert len(list_frame_paths()) == 1
    assert len(list_center_paths(1)) == 1


def test_loot_roll_effect_id_pool(monkeypatch):
    monkeypatch.delenv("TBCC_LOOT_ROLL_EFFECT_ID", raising=False)
    assert DEFAULT_LOOT_ROLL_EFFECT_ID == EFFECT_SPARKLES
    assert EFFECT_SPARKLES in LOOT_ROLL_EFFECT_POOL
    assert "4927184970142712981" in LOOT_ROLL_EFFECT_POOL
    # deterministic pick from pool
    picked = loot_roll_effect_id(rng=random.Random(0))
    assert picked in LOOT_ROLL_EFFECT_POOL
    monkeypatch.setenv("TBCC_LOOT_ROLL_EFFECT_ID", "off")
    assert loot_roll_effect_id() is None
    monkeypatch.setenv("TBCC_LOOT_ROLL_EFFECT_ID", EFFECT_SPARKLES)
    assert loot_roll_effect_id() == EFFECT_SPARKLES
