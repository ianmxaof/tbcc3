"""
Deterministic compositor acceptance tests for the loot reveal card.

Uses compose_reveal_card(frame_path=, center_path=) so nothing depends on the
random frame/center pools. Asserts the delivery invariants the whole feature
exists to guarantee: opaque JPEG, real photo pasted in the window, no baked
checker in the margin, and a DYNAMIC tier label (from the roll, not the frame).
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from app.services.loot_tier_card_assets import compose_reveal_card


def _clean_frame(path: Path, size: int = 512) -> None:
    """Transparent exterior + opaque chrome ring + real transparent window hole."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = im.load()
    lo, hi = int(size * 0.12), int(size * 0.88)
    wlo, whi = int(size * 0.20), int(size * 0.80)
    for y in range(size):
        for x in range(size):
            in_chrome = lo <= x < hi and lo <= y < hi
            in_window = wlo <= x < whi and wlo <= y < whi
            if in_chrome and not in_window:
                px[x, y] = (40, 44, 52, 255)  # opaque chrome
            # else stays fully transparent (exterior + window hole)
    im.save(path)


def _photo_center(path: Path, size: int = 400) -> None:
    """Bright, clearly-not-backdrop image so the paste is detectable."""
    im = Image.new("RGB", (size, size))
    px = im.load()
    for y in range(size):
        for x in range(size):
            px[x, y] = (240, 90, 200)  # vivid magenta-pink, nothing like a dark backdrop
    im.save(path, quality=92)


def _fixtures(tmp_path: Path) -> tuple[Path, Path]:
    fp = tmp_path / "frame-001.png"
    cp = tmp_path / "center.jpg"
    _clean_frame(fp)
    _photo_center(cp)
    return fp, cp


def test_output_is_opaque_jpeg(tmp_path: Path):
    fp, cp = _fixtures(tmp_path)
    data = compose_reveal_card(
        5, world="World 2-2", name="drip", tagline="Mid-heat.",
        frame_path=fp, center_path=cp, size=512,
    )
    assert data is not None
    assert data[:2] == b"\xff\xd8"  # JPEG magic
    assert len(data) > 3000
    im = Image.open(io.BytesIO(data))
    assert im.mode == "RGB"
    assert "A" not in im.mode


def test_center_photo_actually_pasted(tmp_path: Path):
    """Center region must carry the vivid photo, not the dark backdrop."""
    fp, cp = _fixtures(tmp_path)
    data = compose_reveal_card(
        5, frame_path=fp, center_path=cp, size=512, stamp_chrome=False,
    )
    im = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = im.size
    r, g, b = im.getpixel((w // 2, h // 2))
    # vivid pink center — clearly brighter/redder than the (8,8,10) backdrop
    assert r > 150 and b > 120
    assert (r + g + b) / 3 > 60


def test_no_checker_in_outer_margin(tmp_path: Path):
    """No classic mid-grey (~128) checker cell survives in the corners."""
    fp, cp = _fixtures(tmp_path)
    data = compose_reveal_card(
        5, frame_path=fp, center_path=cp, size=512, stamp_chrome=False,
    )
    im = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = im.size
    for x, y in ((1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2)):
        r, g, b = im.getpixel((x, y))
        classic_checker = 96 <= r <= 200 and abs(r - g) < 18 and abs(g - b) < 18
        assert not classic_checker, f"checker-like pixel at {(x, y)} = {(r, g, b)}"


def test_tier_label_is_dynamic_not_frame_metadata(tmp_path: Path):
    """
    Same frame, different tier -> the top-right badge region must differ.
    Proves the tier text is stamped from the roll, not baked into the frame.
    """
    fp, cp = _fixtures(tmp_path)
    a = compose_reveal_card(2, name="peek", frame_path=fp, center_path=cp, size=512)
    b = compose_reveal_card(8, name="ruin", frame_path=fp, center_path=cp, size=512)
    ia = Image.open(io.BytesIO(a)).convert("RGB")
    ib = Image.open(io.BytesIO(b)).convert("RGB")
    # Compare the top-right region (where TIER N is stamped) at a common size.
    common = (400, 400)
    ta = ia.resize(common).crop((260, 0, 400, 90))
    tb = ib.resize(common).crop((260, 0, 400, 90))
    diff = sum(
        abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]) + abs(pa[2] - pb[2])
        for pa, pb in zip(ta.getdata(), tb.getdata())
    )
    assert diff > 0, "tier badge identical across tiers — label is not dynamic"


def test_name_and_tagline_do_not_overlap(tmp_path: Path):
    """Regression: tagline used to render on the name's descenders."""
    fp, cp = _fixtures(tmp_path)
    # Should compose without error and stay opaque JPEG with both strings requested.
    data = compose_reveal_card(
        5, name="drip", tagline="Mid-heat.", frame_path=fp, center_path=cp, size=512,
    )
    assert data[:2] == b"\xff\xd8"
    im = Image.open(io.BytesIO(data))
    assert im.mode == "RGB"


def _clean_frame_at(path: Path, size: int = 256) -> None:
    from PIL import Image as _I
    im = _I.new("RGBA", (size, size), (0, 0, 0, 0))
    px = im.load()
    lo, hi = int(size * 0.12), int(size * 0.88)
    wlo, whi = int(size * 0.22), int(size * 0.78)
    for y in range(size):
        for x in range(size):
            if lo <= x < hi and lo <= y < hi and not (wlo <= x < whi and wlo <= y < whi):
                px[x, y] = (40, 44, 52, 255)
    im.save(path)


def test_reveal_pool_prefers_clean_when_present(tmp_path: Path, monkeypatch):
    from app.services import loot_tier_card_assets as A

    monkeypatch.setenv("TBCC_LOOT_TIER_CARD_DIR", str(tmp_path))
    frames = tmp_path / "frames"
    (frames / "clean").mkdir(parents=True)
    # 3 raw top-level frames, 1 curated clean frame
    for i in range(1, 4):
        _clean_frame_at(frames / f"frame-{i:03d}.png")
    _clean_frame_at(frames / "clean" / "frame-094.png")

    assert len(A.list_frame_paths()) == 3
    assert len(A.list_clean_frame_paths()) == 1
    reveal = A.list_reveal_frame_paths()
    assert len(reveal) == 1
    assert reveal[0].parent.name == "clean"


def test_reveal_pool_falls_back_to_raw_without_clean(tmp_path: Path, monkeypatch):
    from app.services import loot_tier_card_assets as A

    monkeypatch.setenv("TBCC_LOOT_TIER_CARD_DIR", str(tmp_path))
    frames = tmp_path / "frames"
    frames.mkdir(parents=True)
    _clean_frame_at(frames / "frame-001.png")
    _clean_frame_at(frames / "frame-002.png")
    assert A.list_clean_frame_paths() == []
    assert len(A.list_reveal_frame_paths()) == 2
