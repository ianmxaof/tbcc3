#!/usr/bin/env python3
"""Build TBCC extension icons + favicon from a square or landscape master PNG."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ICONS_DIR = ROOT / "icons"
DOCS_MASTER = ROOT / "docs" / "tbcc-icon-master.png"

# Chrome MV3 + gallery favicon flyout
PNG_SIZES = (16, 32, 48, 128)
ICO_SIZES = (16, 32, 48)


def center_crop_square(im: Image.Image) -> Image.Image:
    w, h = im.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return im.crop((left, top, left + side, top + side))


def _background_fill(im: Image.Image) -> tuple[int, ...]:
    """Sample corners so padded edges match the master gradient."""
    w, h = im.size
    pts = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    if im.mode == "RGBA":
        rs, gs, bs, _ = zip(*(im.getpixel(p) for p in pts))
        return (sum(rs) // 4, sum(gs) // 4, sum(bs) // 4, 255)
    rs, gs, bs = zip(*(im.getpixel(p)[:3] for p in pts))
    return (sum(rs) // 4, sum(gs) // 4, sum(bs) // 4)


def fit_to_canvas(im: Image.Image, fill: float = 1.06) -> Image.Image:
    """
    Place the mark on a square canvas.

    fill < 1.0 — inset margin (legacy “breathing room”).
    fill = 1.0 — edge-to-edge on the square master.
    fill > 1.0 — zoom in and center-crop (larger bolt at 16px; Chrome’s rounded mask still clears tips).
    """
    side = im.size[0]
    if fill <= 0 or fill > 1.2:
        raise ValueError("fill must be in (0, 1.2]")

    if fill >= 1.0:
        target = max(side, int(round(side * fill)))
        zoomed = im.resize((target, target), Image.Resampling.LANCZOS)
        left = (target - side) // 2
        top = (target - side) // 2
        return zoomed.crop((left, top, left + side, top + side))

    inner = max(1, int(round(side * fill)))
    scaled = im.resize((inner, inner), Image.Resampling.LANCZOS)
    out = Image.new(im.mode, (side, side), _background_fill(im))
    off = (side - inner) // 2
    out.paste(scaled, (off, off))
    return out


def resize_icon(im: Image.Image, size: int) -> Image.Image:
    out = im.resize((size, size), Image.Resampling.LANCZOS)
    if size <= 16:
        out = out.filter(ImageFilter.UnsharpMask(radius=0.5, percent=150, threshold=1))
    elif size <= 32:
        out = out.filter(ImageFilter.UnsharpMask(radius=0.6, percent=130, threshold=2))
    return out


def build_all(source: Path, *, master_out: Path | None = None, fill: float = 1.06) -> None:
    im = Image.open(source).convert("RGBA")
    square = center_crop_square(im)
    square = fit_to_canvas(square, fill=fill)

    if master_out:
        master = square.resize((1024, 1024), Image.Resampling.LANCZOS)
        master.save(master_out, format="PNG", optimize=True)

    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    png_images: dict[int, Image.Image] = {}
    for size in PNG_SIZES:
        icon = resize_icon(square, size)
        dest = ICONS_DIR / f"icon{size}.png"
        icon.save(dest, format="PNG", optimize=True)
        png_images[size] = icon
        print(f"wrote {dest} ({dest.stat().st_size} bytes)")

    ico_path = ICONS_DIR / "favicon.ico"
    ico_images = [png_images[s].convert("RGBA") for s in ICO_SIZES]
    ico_images[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
        append_images=ico_images[1:],
    )
    print(f"wrote {ico_path} ({ico_path.stat().st_size} bytes)")


def main() -> None:
    default_src = DOCS_MASTER

    p = argparse.ArgumentParser(description="Generate TBCC extension icons from master PNG")
    p.add_argument("source", nargs="?", type=Path, default=default_src, help="Master PNG path")
    p.add_argument("--no-master-copy", action="store_true", help="Skip updating docs/tbcc-icon-master.png")
    p.add_argument(
        "--fill",
        type=float,
        default=1.06,
        metavar="FACTOR",
        help="Mark scale on square canvas: 1.0=full bleed, 1.06=default (larger at 16px), <1 adds margin",
    )
    args = p.parse_args()

    if not args.source.is_file():
        raise SystemExit(f"Source image not found: {args.source}")

    master_out = None if args.no_master_copy else DOCS_MASTER
    build_all(args.source, master_out=master_out, fill=args.fill)
    print("Done. Reload the extension in chrome://extensions")


if __name__ == "__main__":
    main()
