"""Detect window + stamp plates from a border animation reference frame."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# Fallback when ffmpeg / detection fails (brushed metal @ 512px).
_DEFAULT = {
    "window": (0.10, 0.20, 0.90, 0.76),
    "brand_plate": (0.04, 0.05, 0.44, 0.20),
    "badge_plate": (0.56, 0.05, 0.96, 0.26),
    "bottom_plate": (0.16, 0.79, 0.84, 0.92),
}


def _is_key(r: int, g: int, b: int) -> bool:
    """Chroma / matte pixels (magenta, green, pink gutters, near-magenta sparkles)."""
    if r > 130 and b > 130 and g < 110:
        return True
    if g > 170 and r < 110 and b < 110:
        return True
    # Gemini pink/magenta gutters and light magenta haze
    if r > 150 and b > 110 and g < min(r, b) * 0.55:
        if abs(r - b) < 90:
            return True
    if r > 200 and b > 160 and g < 120 and (r - g) > 80:
        return True
    return False


def _is_plate(r: int, g: int, b: int) -> bool:
    if _is_key(r, g, b):
        return False
    m = (r + g + b) / 3
    return 85 < m < 215 and max(r, g, b) - min(r, g, b) < 42


def _bbox_in_region(
    im: Image.Image,
    region: tuple[float, float, float, float],
    *,
    predicate,
) -> tuple[float, float, float, float] | None:
    w, h = im.size
    x0, y0, x1, y1 = region
    rx0, ry0 = int(w * x0), int(h * y0)
    rx1, ry1 = int(w * x1), int(h * y1)
    pts: list[tuple[int, int]] = []
    px = im.load()
    for y in range(ry0, ry1):
        for x in range(rx0, rx1):
            if predicate(*px[x, y]):
                pts.append((x, y))
    if len(pts) < 24:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    pad = max(2, int(min(w, h) * 0.008))
    return (
        max(0, (min(xs) - pad) / w),
        max(0, (min(ys) - pad) / h),
        min(1, (max(xs) + pad) / w),
        min(1, (max(ys) + pad) / h),
    )


def _window_bbox(im: Image.Image) -> tuple[float, float, float, float]:
    w, h = im.size
    work = Image.new("L", (w, h), 255)
    px = im.load()
    for y in range(h):
        for x in range(w):
            if _is_key(*px[x, y]):
                work.putpixel((x, y), 0)
    seed = (w // 2, h // 2)
    if work.getpixel(seed) == 0:
        ImageDraw.floodfill(work, seed, 64)
    inner = work.point(lambda v: 255 if v == 64 else 0)
    bb = inner.getbbox()
    if bb:
        x0, y0, x1, y1 = bb
        if (x1 - x0) > w * 0.2 and (y1 - y0) > h * 0.2:
            return (x0 / w, y0 / h, x1 / w, y1 / h)
    return _DEFAULT["window"]


def detect_border_geometry(im: Image.Image) -> dict[str, tuple[float, float, float, float]]:
    brand = _bbox_in_region(im, (0.0, 0.0, 0.48, 0.28), predicate=_is_plate)
    # Prefer right-rail badge (teal frames) over top-right shield when denser.
    badge_right = _bbox_in_region(im, (0.66, 0.10, 1.0, 0.62), predicate=_is_plate)
    badge_top = _bbox_in_region(im, (0.50, 0.0, 1.0, 0.30), predicate=_is_plate)
    badge = badge_right or badge_top
    bottom = _bbox_in_region(im, (0.08, 0.70, 0.92, 1.0), predicate=_is_plate)
    window = _window_bbox(im)
    out = dict(_DEFAULT)
    if brand:
        out["brand_plate"] = brand
    if badge:
        out["badge_plate"] = badge
    if bottom:
        out["bottom_plate"] = bottom
    out["window"] = window
    return out


def extract_reference_frame(clip: Path, *, offset_s: float = 0.35) -> Path | None:
    if not clip.is_file():
        return None
    td = tempfile.mkdtemp(prefix="tbcc_border_ref_")
    out = Path(td) / "ref.png"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        str(offset_s),
        "-i",
        str(clip),
        "-frames:v",
        "1",
        str(out),
    ]
    try:
        subprocess.run(cmd, check=True, timeout=30, capture_output=True)
    except Exception as e:
        logger.debug("border ref frame extract failed %s: %s", clip.name, e)
        return None
    return out if out.is_file() else None


@lru_cache(maxsize=16)
def geometry_for_border_clip(clip_key: str, mtime_ns: int) -> dict[str, tuple[float, float, float, float]]:
    clip = Path(clip_key)
    ref = extract_reference_frame(clip)
    if ref is None:
        return dict(_DEFAULT)
    try:
        im = Image.open(ref).convert("RGB")
        if max(im.size) != 512:
            im = im.resize((512, 512), Image.Resampling.BILINEAR)
        return detect_border_geometry(im)
    except Exception:
        return dict(_DEFAULT)


def plates_for_border_clip(stasis_clip: Path) -> dict[str, tuple[float, float, float, float]]:
    try:
        st = stasis_clip.stat()
        mtime_ns = int(st.st_mtime_ns)
    except OSError:
        mtime_ns = 0
    return geometry_for_border_clip(str(stasis_clip.resolve()), mtime_ns)


def _card_crop_from_image(im: Image.Image) -> tuple[float, float, float, float]:
    """Tight bbox of non-chroma-key pixels (the visible card chrome)."""
    w, h = im.size
    px = im.load()
    xs: list[int] = []
    ys: list[int] = []
    for y in range(h):
        for x in range(w):
            if not _is_key(*px[x, y]):
                xs.append(x)
                ys.append(y)
    if not xs:
        return (0.0, 0.0, 1.0, 1.0)
    pad = max(1, int(min(w, h) * 0.004))
    x0 = max(0, min(xs) + pad)
    y0 = max(0, min(ys) + pad)
    x1 = min(w, max(xs) - pad)
    y1 = min(h, max(ys) - pad)
    if x1 <= x0 or y1 <= y0:
        return (0.0, 0.0, 1.0, 1.0)
    return (x0 / w, y0 / h, x1 / w, y1 / h)


def card_crop_bbox_px(im: Image.Image) -> tuple[int, int, int, int]:
    """Pixel bbox (x0, y0, x1, y1) of visible chrome on a reference frame."""
    w, h = im.size
    fx0, fy0, fx1, fy1 = _card_crop_from_image(im)
    return (int(fx0 * w), int(fy0 * h), int(fx1 * w), int(fy1 * h))


def _even_dims(x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int, int]:
    """YUV420-safe even width/height."""
    cw = max(2, x1 - x0)
    ch = max(2, y1 - y0)
    cw -= cw % 2
    ch -= ch % 2
    return x0, y0, x0 + cw, y0 + ch


def card_crop_bbox_for_clip(
    clip: Path,
    *,
    offsets_s: tuple[float, ...] = (0.5, 1.5, 3.0),
) -> tuple[int, int, int, int] | None:
    """
    Union chrome bbox across sample frames (handles open vs sustain; drops letterbox).
    Returns pixel crop (x0, y0, x1, y1) in source video coordinates.
    """
    if not clip.is_file():
        return None
    boxes: list[tuple[int, int, int, int]] = []
    for off in offsets_s:
        ref = extract_reference_frame(clip, offset_s=off)
        if ref is None:
            continue
        try:
            im = Image.open(ref).convert("RGB")
            box = card_crop_bbox_px(im)
            if box[2] - box[0] >= 32 and box[3] - box[1] >= 32:
                boxes.append(box)
        except Exception:
            continue
    if not boxes:
        return None
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    w, h = x1 - x0, y1 - y0
    if w < 32 or h < 32:
        return None
    # Reject if crop is nearly full frame (no letterbox to remove)
    try:
        ref0 = extract_reference_frame(clip, offset_s=offsets_s[0])
        if ref0:
            im0 = Image.open(ref0).convert("RGB")
            fw, fh = im0.size
            if w > fw * 0.97 and h > fh * 0.97:
                return None
    except Exception:
        pass
    return _even_dims(x0, y0, x1, y1)


def ffmpeg_chrome_crop_scale_chain(
    crop: tuple[int, int, int, int] | None,
    *,
    size: int,
    fps: int = 24,
    suffix: str = "",
) -> str:
    """
    ffmpeg vf chain: optional chrome crop → uniform scale → square center crop → fps.
    """
    parts: list[str] = []
    if crop is not None:
        x0, y0, x1, y1 = crop
        cw, ch = x1 - x0, y1 - y0
        parts.append(f"crop={cw}:{ch}:{x0}:{y0}")
    parts.append(f"scale={size}:{size}:force_original_aspect_ratio=increase")
    parts.append(f"crop={size}:{size}")
    parts.append(f"fps={fps}")
    chain = ",".join(parts)
    return f"{chain}{suffix}"


@lru_cache(maxsize=16)
def card_crop_frac_for_clip(clip_key: str, mtime_ns: int) -> tuple[float, float, float, float]:
    clip = Path(clip_key)
    ref = extract_reference_frame(clip)
    if ref is None:
        return (0.0, 0.0, 1.0, 1.0)
    try:
        im = Image.open(ref).convert("RGB")
        return _card_crop_from_image(im)
    except Exception:
        return (0.0, 0.0, 1.0, 1.0)


def card_crop_frac(stasis_clip: Path) -> tuple[float, float, float, float]:
    try:
        st = stasis_clip.stat()
        mtime_ns = int(st.st_mtime_ns)
    except OSError:
        mtime_ns = 0
    return card_crop_frac_for_clip(str(stasis_clip.resolve()), mtime_ns)
