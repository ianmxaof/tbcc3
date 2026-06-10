#!/usr/bin/env python3
"""Build TBCC extension icons from the simplified vector mark (flat stroke, no gradient)."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ICONS_DIR = ROOT / "icons"
TRANSPARENT_DIR = ICONS_DIR / "transparent"
DOCS_MASTER = ROOT / "docs" / "tbcc-icon-master.png"
SVG_MARK = ICONS_DIR / "tbcc-mark.svg"

# Brand (Catppuccin Mocha family)
BG = (0x1E, 0x1E, 0x2E, 0xFF)
BLUE = (0x89, 0xB4, 0xFA, 0xFF)
PINK = (0xF5, 0xC2, 0xE7, 0xFF)

PNG_SIZES = (16, 32, 48, 128, 256)
ICO_SIZES = (16, 32, 48, 64, 128, 256)

# Normalized flat-top hex (pointy sides) — matches tbcc-mark.svg
HEX_FRAC = [
    (0.500, 0.086),
    (0.816, 0.270),
    (0.816, 0.637),
    (0.500, 0.820),
    (0.184, 0.637),
    (0.184, 0.270),
]

# 7-vertex thick lightning traced from original master (horizontal middle bar + wide spikes)
BOLT_FRAC = [
    (0.865, 0.028),  # top tip
    (0.728, 0.438),  # right inner jog
    (0.645, 0.555),  # middle bottom-right (parallelogram)
    (0.118, 0.972),  # bottom tip
    (0.252, 0.555),  # middle bottom-left
    (0.325, 0.425),  # middle top-left
    (0.478, 0.265),  # upper-left shoulder
]

# Mark scale around center (1.0 = SVG coords; >1 zooms for Chrome toolbar fill)
MARK_BLEED = 0.94


def _scale_points(frac: list[tuple[float, float]], size: int, bleed: float) -> list[tuple[float, float]]:
    c = 0.5
    s = float(size)
    return [(((x - c) * bleed + c) * s, ((y - c) * bleed + c) * s) for x, y in frac]


def _stroke_width(size: int) -> float:
    """Thicker at small sizes so the hex ring stays visible at 16px."""
    if size <= 16:
        return 2.0
    if size <= 32:
        return 3.0
    return max(4.0, round(size * 28 / 512))


def _draw_stroked_polygon(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[float, float]],
    color: tuple[int, ...],
    width: float,
    punch: tuple[int, ...],
) -> None:
    """Thick stroke via outer/inner polygon; inner filled with punch (bg or transparent)."""
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    half = width / 2.0
    outer: list[tuple[float, float]] = []
    inner: list[tuple[float, float]] = []
    for x, y in points:
        dx, dy = x - cx, y - cy
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        outer.append((x + ux * half, y + uy * half))
        inner.append((x - ux * half, y - uy * half))
    draw.polygon(outer, fill=color)
    draw.polygon(inner, fill=punch)


def render_mark(size: int, *, background: bool, bleed: float = MARK_BLEED) -> Image.Image:
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if background:
        bg_layer = Image.new("RGBA", (size, size), BG)
        im = Image.alpha_composite(im, bg_layer)

    hex_pts = _scale_points(HEX_FRAC, size, bleed)
    bolt_pts = _scale_points(BOLT_FRAC, size, bleed)
    punch: tuple[int, ...] = BG if background else (0, 0, 0, 0)

    hex_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    _draw_stroked_polygon(ImageDraw.Draw(hex_layer), hex_pts, BLUE, _stroke_width(size), punch)

    bolt_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(bolt_layer).polygon(bolt_pts, fill=PINK)

    im = Image.alpha_composite(im, hex_layer)
    im = Image.alpha_composite(im, bolt_layer)
    return im


def build_simplified(*, bleed: float = MARK_BLEED, transparent_dir: Path = TRANSPARENT_DIR) -> dict[int, Image.Image]:
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    transparent_dir.mkdir(parents=True, exist_ok=True)

    with_bg: dict[int, Image.Image] = {}
    no_bg: dict[int, Image.Image] = {}

    for size in PNG_SIZES:
        bg_icon = render_mark(size, background=True, bleed=bleed)
        tr_icon = render_mark(size, background=False, bleed=bleed)

        bg_path = ICONS_DIR / f"icon{size}.png"
        tr_path = transparent_dir / f"icon{size}.png"
        bg_icon.save(bg_path, format="PNG", optimize=True)
        tr_icon.save(tr_path, format="PNG", optimize=True)
        with_bg[size] = bg_icon
        no_bg[size] = tr_icon
        print(f"wrote {bg_path} ({bg_path.stat().st_size} bytes)")
        print(f"wrote {tr_path} ({tr_path.stat().st_size} bytes)")

    ico_path = ICONS_DIR / "favicon.ico"
    ico_images = []
    for s in ICO_SIZES:
        if s not in with_bg:
            with_bg[s] = render_mark(s, background=True, bleed=bleed)
        ico_images.append(with_bg[s].convert("RGBA"))
    ico_images[-1].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
        append_images=ico_images[:-1],
    )
    print(f"wrote {ico_path} ({ico_path.stat().st_size} bytes)")

    master = render_mark(1024, background=True, bleed=bleed)
    master.save(DOCS_MASTER, format="PNG", optimize=True)
    print(f"wrote {DOCS_MASTER} ({DOCS_MASTER.stat().st_size} bytes)")

    return with_bg


def main() -> None:
    p = argparse.ArgumentParser(description="Generate TBCC simplified vector icons (with + transparent sets)")
    p.add_argument(
        "--mark-bleed",
        type=float,
        default=MARK_BLEED,
        metavar="FACTOR",
        help="Mark scale on canvas (default 0.94 — fills Chrome 16px toolbar)",
    )
    args = p.parse_args()

    if not SVG_MARK.is_file():
        raise SystemExit(f"Missing vector source: {SVG_MARK}")

    build_simplified(bleed=args.mark_bleed)
    print("Done. Reload the extension in chrome://extensions")


if __name__ == "__main__":
    main()
