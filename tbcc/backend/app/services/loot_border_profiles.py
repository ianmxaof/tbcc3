"""Per-border animation profiles: window hole + stamp plate geometry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.loot_card_frame_styles import StampLayout

# Fractional rects (x0, y0, x1, y1) on a square card, 0..1.
# Measured from brushed_metal_stasis_sparkle stasis reference @ 512px.


@dataclass(frozen=True)
class BorderRevealProfile:
    profile_id: str
    window: tuple[float, float, float, float]
    brand_plate: tuple[float, float, float, float]
    badge_plate: tuple[float, float, float, float]
    bottom_plate: tuple[float, float, float, float]
    stamp_layout: StampLayout
    footer_plate: tuple[float, float, float, float] | None = None
    stamp_brand: bool = True


_BRUSHED_METAL_LAYOUT = StampLayout(
    style_id="brushed_metal",
    brand_x=0.05,
    brand_y=0.06,
    brand_max_w=0.34,
    brand_font_h=0.055,
    brand_min_font=11,
    show_hub=True,
    badge_x1=0.94,
    badge_y0=0.06,
    badge_h=0.042,
    world_below_badge=False,
    name_font_h=0.062,
)

BRUSHED_METAL_STASIS_SPARKLE = BorderRevealProfile(
    profile_id="brushed_metal_stasis_sparkle",
    window=(0.10, 0.20, 0.90, 0.76),
    brand_plate=(0.04, 0.05, 0.44, 0.20),
    badge_plate=(0.56, 0.05, 0.96, 0.26),
    bottom_plate=(0.16, 0.79, 0.84, 0.92),
    footer_plate=(0.16, 0.92, 0.84, 0.98),
    stamp_layout=_BRUSHED_METAL_LAYOUT,
    stamp_brand=True,
)

_PROFILES: list[BorderRevealProfile] = [
    BRUSHED_METAL_STASIS_SPARKLE,
]


def _border_base(stem: str) -> str:
    s = stem.lower()
    for suffix in ("_open", "-open", "_stasis", "-stasis", "_single", "-single"):
        if s.endswith(suffix):
            return s[: -len(suffix)]
    return s


def profile_for_border(path: Path | None) -> BorderRevealProfile | None:
    if path is None:
        return None
    stem = _border_base(path.stem)
    for profile in _PROFILES:
        if profile.profile_id in stem or stem in profile.profile_id:
            return profile
    if "brushed_metal" in stem and "sparkle" in stem:
        return BRUSHED_METAL_STASIS_SPARKLE
    if "loot_god" in stem or "project_aof" in stem:
        return BRUSHED_METAL_STASIS_SPARKLE
    return None


def frac_rect_to_px(
    rect: tuple[float, float, float, float], size: int
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = rect
    return (
        int(size * x0),
        int(size * y0),
        int(size * x1),
        int(size * y1),
    )
