"""Per-frame stamp layouts: classify border art → style → x,y placement."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class StampLayout:
    """Fractional coords relative to final card (0..1)."""

    style_id: str
    brand_x: float
    brand_y: float
    brand_max_w: float
    brand_font_h: float
    brand_min_font: int
    show_hub: bool
    badge_x1: float  # right edge anchor (badge aligns right to this)
    badge_y0: float
    badge_h: float
    world_below_badge: bool
    name_font_h: float


# Style A — clean cyan / simple plates (best performers: frame-001 class).
_LAYOUT_A = StampLayout(
    style_id="a",
    brand_x=0.04,
    brand_y=0.05,
    brand_max_w=0.42,
    brand_font_h=0.105,
    brand_min_font=14,
    show_hub=True,
    badge_x1=0.96,
    badge_y0=0.05,
    badge_h=0.055,
    world_below_badge=True,
    name_font_h=0.095,
)

# Style B — copper / bronze ornate (heavy top-left plate; brand smaller, lower).
_LAYOUT_B = StampLayout(
    style_id="b",
    brand_x=0.025,
    brand_y=0.085,
    brand_max_w=0.34,
    brand_font_h=0.078,
    brand_min_font=12,
    show_hub=False,
    badge_x1=0.94,
    badge_y0=0.04,
    badge_h=0.052,
    world_below_badge=True,
    name_font_h=0.088,
)

# Style C — purple neon ornate.
_LAYOUT_C = StampLayout(
    style_id="c",
    brand_x=0.035,
    brand_y=0.065,
    brand_max_w=0.36,
    brand_font_h=0.085,
    brand_min_font=13,
    show_hub=True,
    badge_x1=0.95,
    badge_y0=0.045,
    badge_h=0.05,
    world_below_badge=True,
    name_font_h=0.09,
)

# Style D — teal / alien organic frames.
_LAYOUT_D = StampLayout(
    style_id="d",
    brand_x=0.04,
    brand_y=0.06,
    brand_max_w=0.38,
    brand_font_h=0.09,
    brand_min_font=13,
    show_hub=True,
    badge_x1=0.93,
    badge_y0=0.055,
    badge_h=0.048,
    world_below_badge=True,
    name_font_h=0.085,
)

STAMP_LAYOUTS: dict[str, StampLayout] = {
    "a": _LAYOUT_A,
    "b": _LAYOUT_B,
    "c": _LAYOUT_C,
    "d": _LAYOUT_D,
}

# Hand-tuned overrides for known frame stems (operator eyeballed).
_FRAME_STYLE_OVERRIDES: dict[str, str] = {
    "frame-001": "a",
    "frame-003": "a",
    "frame-005": "a",
    "frame-007": "a",
    "mag-009": "a",
    "mag-019": "a",
    "mag-042": "a",
    "mag-052": "a",
    "mag-062": "a",
    "mag-076": "a",
    "mag-001": "c",
    "mag-002": "c",
    "mag-040": "c",
    "mag-046": "c",
    "mag-054": "c",
    "mag-069": "c",
    "mag-082": "c",
    "mag-006": "b",
    "mag-020": "b",
    "mag-053": "b",
    "mag-070": "b",
    "mag-071": "b",
    "mag-072": "b",
    "mag-009": "a",
}


def classify_frame_style(frame: Image.Image, *, path: Path | None = None) -> str:
    """Return style id a–d from border accent colors + optional filename override."""
    if path is not None:
        stem = path.stem.lower()
        if stem in _FRAME_STYLE_OVERRIDES:
            return _FRAME_STYLE_OVERRIDES[stem]

    im = frame.convert("RGBA")
    if max(im.size) > 256:
        im = im.resize((256, 256), Image.Resampling.BILINEAR)
    w, h = im.size
    px = im.load()

    rs = gs = bs = n = 0
    for y in range(0, max(1, h // 6)):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 120:
                continue
            mx, mn = max(r, g, b), min(r, g, b)
            if mx - mn < 12:
                continue
            rs += r
            gs += g
            bs += b
            n += 1
    if n < 8:
        return "a"

    ar, ag, ab = rs / n, gs / n, bs / n
    if ar > ag + 18 and ar > ab + 10 and ar > 95:
        return "b"
    if ab > ar + 12 and ab > ag:
        return "c"
    if ag > ar + 8 and ag > ab:
        return "d"
    if ab > ar + 6:
        return "a"
    return "a"


def layout_for_frame(frame: Image.Image, *, path: Path | None = None) -> StampLayout:
    sid = classify_frame_style(frame, path=path)
    return STAMP_LAYOUTS.get(sid, _LAYOUT_A)
