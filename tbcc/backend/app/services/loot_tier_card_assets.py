"""Resolve / compose loot reveal cards: transparent frame over band center art."""

from __future__ import annotations

import io
import os
import random
from collections import deque
from pathlib import Path

from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from app.services.loot_card_frame_styles import StampLayout

# Card-face inventory bands (not 10 per-tier pools).
CENTER_BAND_LOW = "low"  # tiers 1–5
CENTER_BAND_HIGH = "high"  # tiers 6–9
CENTER_BAND_GODROLL = "godroll"  # tier 10
CENTER_BANDS = (CENTER_BAND_LOW, CENTER_BAND_HIGH, CENTER_BAND_GODROLL)


def center_band_for_tier(tier: int) -> str:
    t = max(1, min(10, int(tier)))
    if t >= 10:
        return CENTER_BAND_GODROLL
    if t >= 6:
        return CENTER_BAND_HIGH
    return CENTER_BAND_LOW


def loot_tier_card_dir() -> Path:
    override = (os.getenv("TBCC_LOOT_TIER_CARD_DIR") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "data" / "loot_tier_cards"


def frames_dir() -> Path:
    override = (os.getenv("TBCC_LOOT_CARD_FRAMES_DIR") or "").strip()
    if override:
        return Path(override)
    return loot_tier_card_dir() / "frames"


def centers_root() -> Path:
    override = (os.getenv("TBCC_LOOT_CARD_CENTERS_DIR") or "").strip()
    return Path(override) if override else (loot_tier_card_dir() / "centers")


def centers_dir(tier: int | None = None, *, band: str | None = None) -> Path:
    """
    Root centers/ when tier/band omitted.
    Prefer band folders: centers/low|high|godroll.
    """
    root = centers_root()
    if band:
        return root / str(band)
    if tier is None:
        return root
    return root / center_band_for_tier(tier)


def ensure_center_band_dirs() -> list[Path]:
    root = centers_root()
    out: list[Path] = []
    for name in CENTER_BANDS:
        d = root / name
        d.mkdir(parents=True, exist_ok=True)
        readme = d / "README.txt"
        if not readme.exists():
            if name == CENTER_BAND_LOW:
                tip = "Tiers 1–5 (trash → mid). Phone-cam / leak energy OK.\n"
            elif name == CENTER_BAND_HIGH:
                tip = "Tiers 6–9 (dense / production heat).\n"
            else:
                tip = "Tier 10 godroll only — max dopamine stills.\n"
            readme.write_text(
                f"LOOT CARD CENTER BAND = {name}\n{tip}"
                "Drop .png/.jpg/.webp here. One random file is composited under a "
                "random transparent frame on each roll.\n",
                encoding="utf-8",
            )
        out.append(d)
    (root / "_any").mkdir(parents=True, exist_ok=True)
    return out


def resolve_tier_card_path(tier: int) -> Path | None:
    """
    Look for a clean art card for rarity tier 1–10.

    Filenames tried (first hit wins), under TBCC_LOOT_TIER_CARD_DIR or
    app/data/loot_tier_cards/:
      tier-{n}.png, t{n}.png, tier-{n}.webp, t{n}.webp
    """
    t = max(1, min(10, int(tier)))
    root = loot_tier_card_dir()
    if not root.is_dir():
        return None
    candidates = (
        f"tier-{t}.png",
        f"t{t}.png",
        f"tier-{t}.webp",
        f"t{t}.webp",
        f"tier-{t}.jpg",
        f"t{t}.jpg",
    )
    for name in candidates:
        path = root / name
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def _list_images_in(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(folder.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() not in _IMAGE_EXTS:
            continue
        if p.name.lower() == "readme.txt":
            continue
        if p.stat().st_size <= 0:
            continue
        out.append(p)
    return out


def list_frame_paths() -> list[Path]:
    """All raw top-level frames (frames/frame-*.png). Subdirs (clean/, _*) excluded."""
    root = frames_dir()
    if not root.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(root.iterdir()):
        if not p.is_file():
            continue
        if p.name.startswith("_"):
            continue
        if p.suffix.lower() not in _IMAGE_EXTS:
            continue
        if p.stat().st_size <= 0:
            continue
        out.append(p)
    return out


def list_clean_frame_paths() -> list[Path]:
    """Curated structurally-clean pool (frames/clean/), built by audit_loot_card_frames.

    These are hand-vetted: real center hole, no baked checker, no baked tier badge —
    so a random pick can never contradict the rolled tier (the wrong-tier-label bug).
    """
    root = frames_dir() / "clean"
    if not root.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(root.iterdir()):
        if not p.is_file() or p.name.startswith("_"):
            continue
        if p.suffix.lower() not in _IMAGE_EXTS or p.stat().st_size <= 0:
            continue
        out.append(p)
    return out


def list_blank_plate_frame_paths() -> list[Path]:
    """Blank-plate chroma-keyed frames (mag-*.png) — no baked tier/name text."""
    return [p for p in list_clean_frame_paths() if p.name.lower().startswith("mag-")]


def _frame_chroma_halo_frac(path: Path) -> float:
    """Fraction of top chrome band that is near-black opaque (chroma-key residue)."""
    try:
        im = Image.open(path).convert("RGBA")
        if max(im.size) > 512:
            im = im.resize((512, 512), Image.Resampling.BILINEAR)
        w, h = im.size
        band_h = max(1, h // 7)
        px = im.load()
        dark_opaque = total = 0
        for y in range(band_h):
            for x in range(w):
                r, g, b, a = px[x, y]
                if a < 40:
                    continue
                total += 1
                if r < 28 and g < 28 and b < 28:
                    dark_opaque += 1
        return dark_opaque / max(1, total)
    except Exception:
        return 1.0


def list_reveal_frame_paths() -> list[Path]:
    """Frames to composite: blank-plate mag-* when present, else clean/, else raw."""
    blank = list_blank_plate_frame_paths()
    # Drop mag frames with heavy chroma-key halos (black scribbles in top band).
    if blank:
        good = [p for p in blank if _frame_chroma_halo_frac(p) < 0.06]
        if len(good) >= 8:
            return good
        if good:
            return good
    clean = list_clean_frame_paths()
    return clean if clean else list_frame_paths()


def reveal_frame_pool_kind() -> str:
    """Label for build_reveal_card_png notes: blank | clean | raw."""
    blank = list_blank_plate_frame_paths()
    if blank:
        good = [p for p in blank if _frame_chroma_halo_frac(p) < 0.06]
        reveal = list_reveal_frame_paths()
        if reveal and all(p.name.lower().startswith("mag-") for p in reveal):
            return "blank"
    clean = list_clean_frame_paths()
    return "clean" if clean else "raw"


def _is_placeholder_center(path: Path) -> bool:
    """Migrated sealed tier-card seeds are not usable NSFW stills."""
    name = path.name.lower()
    if name.startswith("migrated-") or "_seed-from-tier-" in name:
        return True
    # Tiny PNGs are almost always the sealed placeholders (~30KB), not photos.
    try:
        if path.suffix.lower() == ".png" and path.stat().st_size < 80_000:
            return True
    except OSError:
        return True
    return False


def list_center_paths(tier: int) -> list[Path]:
    """
    Centers for a rolled tier:
      1) centers/{low|high|godroll}/  (real stills preferred)
      2) legacy centers/t{N}/ (migration)
      3) centers/_any/
      4) static tier-{N}.png

    Placeholder migrated seeds are skipped when any real still exists.
    """
    t = max(1, min(10, int(tier)))
    band = center_band_for_tier(t)
    raw = _list_images_in(centers_dir(band=band))
    real = [p for p in raw if not _is_placeholder_center(p)]
    out = real if real else raw
    if not out:
        out = _list_images_in(centers_root() / f"t{t}")
    if not out:
        out = _list_images_in(centers_root() / "_any")
    if not out:
        legacy = resolve_tier_card_path(t)
        if legacy is not None:
            out.append(legacy)
    return out


def _cover_resize(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    tw, th = size
    w, h = im.size
    if w <= 0 or h <= 0:
        return Image.new("RGBA", (tw, th), (20, 20, 20, 255))
    scale = max(tw / w, th / h)
    nw, nh = max(1, int(w * scale + 0.5)), max(1, int(h * scale + 0.5))
    resized = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = max(0, (nw - tw) // 2)
    top = max(0, (nh - th) // 2)
    return resized.crop((left, top, left + tw, top + th))


def _is_green_px(r: int, g: int, b: int) -> bool:
    return (g > 180 and r < 100 and b < 100) or (g > 160 and g > r + 50 and g > b + 50)


def _is_void_px(r: int, g: int, b: int, a: int, neigh_means: tuple[int, ...]) -> bool:
    """
    True for real alpha holes, chroma-green, or Gemini/Photoshop checker cells
    that were baked as opaque grey RGB (the Telegram-looking checkerboard).

    Solid metal/silver chrome is low-chroma too — only treat grey as void when a
    sharp neighbour luminance step says it's a checker cell.
    """
    if a < 40:
        return True
    if _is_green_px(r, g, b):
        return True
    mx, mn = max(r, g, b), min(r, g, b)
    chroma = mx - mn
    mean = (r + g + b) // 3
    if chroma >= 28:
        return False
    # Include dark checker cells (often ~60–90) not just light ones
    if not (40 <= mean <= 230):
        return False
    if not neigh_means:
        return False
    # Checker cells alternate light/dark; brushed metal does not jump this hard.
    return any(abs(mean - nm) >= 18 for nm in neigh_means)


def sanitize_frame_alpha(frame: Image.Image) -> Image.Image:
    """
    Punch baked checker / green / exterior void to real alpha=0.

    Does NOT rectangular-wipe the art window — that deletes the inner chrome lip
    and makes the still look pasted *on top of* the border.
    """
    im = frame.convert("RGBA")
    w, h = im.size
    px = im.load()
    corner_a = px[0, 0][3]
    mid_a = px[w // 2, h // 2][3]
    already_clean = corner_a < 40 and mid_a < 40
    if already_clean:
        return im

    means = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            r, g, b, _a = px[x, y]
            means[y][x] = (r + g + b) // 3

    for y in range(h):
        row = means[y]
        for x in range(w):
            r, g, b, a = px[x, y]
            neigh: list[int] = []
            if x + 1 < w:
                neigh.append(row[x + 1])
            if y + 1 < h:
                neigh.append(means[y + 1][x])
            if x > 0:
                neigh.append(row[x - 1])
            if y > 0:
                neigh.append(means[y - 1][x])
            if _is_void_px(r, g, b, a, tuple(neigh)):
                px[x, y] = (r, g, b, 0)

    # Exterior baked checker: flood from edges through light greys / holes.
    walk = Image.new("L", (w, h), 0)
    wp = walk.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            mx, mn = max(r, g, b), min(r, g, b)
            mean = (r + g + b) // 3
            if a < 40 or _is_green_px(r, g, b) or (mx - mn < 25 and mean >= 125):
                wp[x, y] = 255
    ext = [[False] * w for _ in range(h)]
    q: deque[tuple[int, int]] = deque()
    for seed in (
        (0, 0),
        (w - 1, 0),
        (0, h - 1),
        (w - 1, h - 1),
        (w // 2, 0),
        (w // 2, h - 1),
        (0, h // 2),
        (w - 1, h // 2),
    ):
        sx, sy = seed
        if wp[sx, sy] == 255 and not ext[sy][sx]:
            ext[sy][sx] = True
            q.append((sx, sy))
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and wp[nx, ny] == 255 and not ext[ny][nx]:
                ext[ny][nx] = True
                q.append((nx, ny))
    for y in range(h):
        for x in range(w):
            if ext[y][x]:
                r, g, b, _a = px[x, y]
                px[x, y] = (r, g, b, 0)

    # Soft-clear only near-neutral residue *inside* the detected window, keeping
    # saturated neon / metal lip pixels (chroma >= 28 or very dark metal).
    x0, y0, x1, y1 = _window_bbox(im)
    if (x1 - x0) >= int(w * 0.92) or (y1 - y0) >= int(h * 0.92):
        x0, y0, x1, y1 = int(w * 0.18), int(h * 0.18), int(w * 0.82), int(h * 0.82)
    # Inset so we don't nibble the chrome ring
    inset = max(4, int(min(x1 - x0, y1 - y0) * 0.04))
    for y in range(y0 + inset, y1 - inset):
        for x in range(x0 + inset, x1 - inset):
            r, g, b, a = px[x, y]
            if a < 40:
                continue
            mx, mn = max(r, g, b), min(r, g, b)
            mean = (r + g + b) // 3
            if mx - mn < 28 and 50 <= mean <= 220:
                px[x, y] = (r, g, b, 0)

    # Chroma-key halos: near-black opaque pixels touching real transparency.
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 40 or r > 32 or g > 32 or b > 32:
                continue
            touches_void = False
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and px[nx, ny][3] < 40:
                    touches_void = True
                    break
            if touches_void:
                px[x, y] = (r, g, b, 0)

    # Band scrub: kill near-black speckle/trails in top/bottom chrome (not colored neon).
    band_h = max(8, h // 8)
    for y in range(h):
        in_band = y < band_h or y >= h - band_h
        if not in_band:
            continue
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 80 or r > 38 or g > 38 or b > 38:
                continue
            mx, mn = max(r, g, b), min(r, g, b)
            if mx - mn > 35:
                continue
            px[x, y] = (r, g, b, 0)
    return im


def key_near_black_to_alpha(frame: Image.Image, *, threshold: int = 18) -> Image.Image:
    """Turn solid black fills (Gemini 'bg removed' JPEGs) into real alpha holes."""
    im = frame.convert("RGBA")
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r <= threshold and g <= threshold and b <= threshold:
                px[x, y] = (r, g, b, 0)
    return im


def _window_bbox(frame_rgba: Image.Image) -> tuple[int, int, int, int]:
    """
    Bounding box of the *inner* art window.

    Punched frames are transparent both outside the chrome and inside the
    window. Naïve getbbox(transparent) returns the full canvas — then the
    center still is pasted under the exterior punch and Telegram looks like
    an empty neon border. Flood-fill exterior transparency from the edges so
    only the interior hole remains.
    """
    w, h = frame_rgba.size
    alpha = frame_rgba.getchannel("A")
    # 0 = transparent candidate, 255 = chrome / keep
    work = Image.new("L", (w, h), 255)
    work.paste(0, mask=alpha.point(lambda a: 255 if a < 40 else 0))

    # Mark exterior punch: flood-fill transparent regions that touch the border.
    for seed in (
        (0, 0),
        (w - 1, 0),
        (0, h - 1),
        (w - 1, h - 1),
        (w // 2, 0),
        (w // 2, h - 1),
        (0, h // 2),
        (w - 1, h // 2),
    ):
        if work.getpixel(seed) == 0:
            ImageDraw.floodfill(work, seed, 64)

    # Remaining 0s = interior window only
    inner = work.point(lambda v: 255 if v == 0 else 0)
    bbox = inner.getbbox()
    if bbox:
        x0, y0, x1, y1 = bbox
        touches_edge = x0 <= 1 or y0 <= 1 or x1 >= w - 1 or y1 >= h - 1
        if (x1 - x0) >= 8 and (y1 - y0) >= 8 and not touches_edge:
            return bbox

    # Fallback: inset from opaque chrome extent
    chrome = alpha.point(lambda a: 255 if a >= 40 else 0)
    chrome_bbox = chrome.getbbox()
    if chrome_bbox:
        cx0, cy0, cx1, cy1 = chrome_bbox
        # If chrome itself spans the full canvas (baked edge junk), use fixed inset.
        if cx0 <= 2 and cy0 <= 2 and cx1 >= w - 2 and cy1 >= h - 2:
            return (int(w * 0.14), int(h * 0.14), int(w * 0.86), int(h * 0.86))
        pad_x = max(10, int((cx1 - cx0) * 0.16))
        pad_y = max(10, int((cy1 - cy0) * 0.16))
        return (
            min(w - 2, cx0 + pad_x),
            min(h - 2, cy0 + pad_y),
            max(cx0 + pad_x + 1, cx1 - pad_x),
            max(cy0 + pad_y + 1, cy1 - pad_y),
        )

    return (int(w * 0.18), int(h * 0.18), int(w * 0.82), int(h * 0.82))


def _try_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for name in (
        "arialbd.ttf",
        "Arial Bold.ttf",
        "DejaVuSans-Bold.ttf",
        # Linux/Docker: no Windows fonts — try common absolute paths
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "segoeui.ttf",
        "arial.ttf",
        "DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    # No system TTF (bare Docker image): Pillow >=10.1 ships DejaVu and honours size.
    # Without the size arg load_default() is a fixed ~10px bitmap => invisible stamps.
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # older Pillow
        return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    if hasattr(draw, "textlength"):
        return int(draw.textlength(text, font=font))
    box = draw.textbbox((0, 0), text, font=font)
    return int(box[2] - box[0])


def _text_height(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return int(box[3] - box[1])


def _world_coord_compact(world_s: str) -> str:
    """'World 4-1' → '4-1' for compact badge subtitle."""
    import re

    s = (world_s or "").strip()
    if not s:
        return ""
    m = re.match(r"^(?:world\s+)?(\d+)\s*-\s*(\d+)\s*$", s, re.I)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.match(r"^(\d+)\s*-\s*(\d+)\s*$", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return s


def _world_badge_lines(world_s: str) -> tuple[str, str]:
    """Split 'World 2-1' → ('World', '2  -  1') for stacked badge text."""
    import re

    s = (world_s or "").strip()
    if not s:
        return "", ""
    m = re.match(r"^(world)\s+(\d+)\s*-\s*(\d+)\s*$", s, re.I)
    if m:
        return m.group(1).title(), f"{m.group(2)}  -  {m.group(3)}"
    m = re.match(r"^(\d+)\s*-\s*(\d+)\s*$", s)
    if m:
        return "", f"{m.group(1)}  -  {m.group(2)}"
    return s, ""


def _badge_plate_lines(tier: int, world_s: str) -> list[str]:
    lines = [f"TIER {tier}"]
    world_line, coord_line = _world_badge_lines(world_s)
    if world_line:
        lines.append(world_line)
    if coord_line:
        lines.append(coord_line)
    elif world_s.strip() and not world_line:
        lines.append(world_s.strip())
    return lines


def _draw_badge_plate_stack(
    draw: ImageDraw.ImageDraw,
    *,
    plate: tuple[int, int, int, int],
    tier: int,
    world_s: str,
    ch: int,
) -> None:
    """Text-only tier/world stack centered inside a border badge plate."""
    px0, py0, px1, py1 = plate
    pw, ph = max(1, px1 - px0), max(1, py1 - py0)
    lines = _badge_plate_lines(tier, world_s)
    tier_font = _fit_font(draw, lines[0], int(pw * 0.92), max(10, int(ph * 0.18)), 9)
    sub_font = _fit_font(
        draw,
        max((ln for ln in lines[1:]), key=len, default="World"),
        int(pw * 0.9),
        max(8, int(ph * 0.12)),
        8,
    )
    gap = max(2, int(ph * 0.035))
    heights = [_text_height(draw, ln, tier_font if i == 0 else sub_font) for i, ln in enumerate(lines)]
    block_h = sum(heights) + gap * max(0, len(lines) - 1)
    y = py0 + max(2, (ph - block_h) // 2)
    for i, ln in enumerate(lines):
        font = tier_font if i == 0 else sub_font
        fill = (240, 255, 245, 255) if i == 0 else (210, 225, 235, 240)
        lw = _text_width(draw, ln, font)
        x = px0 + max(2, (pw - lw) // 2)
        _draw_text_outlined(draw, (x, y), ln, font=font, fill=fill, thin=True)
        y += heights[i] + gap


def _draw_sunken_laser_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    font: ImageFont.ImageFont,
) -> None:
    """Engraved / laser-etched into metal — dark inset with edge highlight."""
    x, y = xy
    draw.text((x + 2, y + 2), text, font=font, fill=(18, 20, 24, 200))
    draw.text((x + 1, y + 1), text, font=font, fill=(38, 42, 48, 230))
    draw.text((x - 1, y - 1), text, font=font, fill=(145, 152, 162, 90))
    draw.text((x, y), text, font=font, fill=(62, 68, 76, 255))


def _draw_sunken_badge_plate(
    draw: ImageDraw.ImageDraw,
    *,
    plate: tuple[int, int, int, int],
    tier: int,
    world_s: str,
) -> None:
    """
    Border badge: large lasered tier digit + compact world coord (e.g. 7 / 4-1).
    Text sits in the upper portion of the plate (shield tapers to a point below).
    """
    px0, py0, px1, py1 = plate
    pw, ph = max(1, px1 - px0), max(1, py1 - py0)
    tier_s = str(max(1, min(10, int(tier))))
    coord_s = _world_coord_compact(world_s)
    text_h = max(8, int(ph * 0.62))
    tier_font = _fit_font(draw, tier_s, int(pw * 0.82), text_h, 12)
    tier_h = _text_height(draw, tier_s, tier_font)
    sub_h = 0
    sub_font = tier_font
    gap = max(1, int(ph * 0.04))
    if coord_s:
        sub_font = _fit_font(draw, coord_s, int(pw * 0.72), max(8, int(ph * 0.14)), 7)
        sub_h = _text_height(draw, coord_s, sub_font)
    block_h = tier_h + (gap + sub_h if coord_s else 0)
    # Upper band — leave tapered point at bottom empty
    band_bottom = py0 + int(ph * 0.72)
    y = py0 + max(2, (band_bottom - py0 - block_h) // 2)
    tw = _text_width(draw, tier_s, tier_font)
    _draw_sunken_laser_text(draw, (px0 + (pw - tw) // 2, y), tier_s, font=tier_font)
    if coord_s:
        sw = _text_width(draw, coord_s, sub_font)
        _draw_sunken_laser_text(
            draw,
            (px0 + (pw - sw) // 2, y + tier_h + gap),
            coord_s,
            font=sub_font,
        )


def _draw_text_outlined(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int] = (245, 245, 245, 255),
    outline: tuple[int, int, int, int] = (0, 0, 0, 140),
    thin: bool = False,
) -> None:
    x, y = xy
    offsets = ((-1, 0), (1, 0), (0, -1), (0, 1)) if thin else (
        (-1, 0), (1, 0), (0, -1), (0, 1), (1, 1), (-1, -1)
    )
    for ox, oy in offsets:
        draw.text((x + ox, y + oy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)


def _solid_chrome_bbox(frame_rgba: Image.Image) -> tuple[int, int, int, int]:
    """Bounding box of opaque frame chrome (alpha), for stamp placement."""
    chrome = frame_rgba.getchannel("A").point(lambda a: 255 if a >= 40 else 0)
    bbox = chrome.getbbox()
    w, h = frame_rgba.size
    if not bbox:
        return (0, 0, w, h)
    pad = max(2, int(min(w, h) * 0.008))
    x0, y0, x1, y1 = bbox
    return (
        max(0, x0 - pad),
        max(0, y0 - pad),
        min(w, x1 + pad),
        min(h, y1 + pad),
    )


def _content_trim_bbox(
    rgb: Image.Image,
    *,
    backdrop: tuple[int, int, int] = (0, 0, 0),
    tol: int = 18,
) -> tuple[int, int, int, int]:
    """Tight crop to non-backdrop pixels (drops exterior void/checker fill)."""
    w, h = rgb.size
    px = rgb.load()
    br, bg, bb = backdrop
    minx, miny, maxx, maxy = w, h, -1, -1
    step = 2
    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b = px[x, y]
            if abs(r - br) <= tol and abs(g - bg) <= tol and abs(b - bb) <= tol:
                continue
            # also treat classic mid-grey checker cells as void for trim
            mx, mn = max(r, g, b), min(r, g, b)
            mean = (r + g + b) // 3
            if mx - mn < 18 and 70 <= mean <= 210:
                continue
            if x < minx:
                minx = x
            if y < miny:
                miny = y
            if x > maxx:
                maxx = x
            if y > maxy:
                maxy = y
    if maxx < minx:
        return (0, 0, w, h)
    pad = max(2, int(min(w, h) * 0.01))
    return (
        max(0, minx - pad),
        max(0, miny - pad),
        min(w, maxx + pad + 1),
        min(h, maxy + pad + 1),
    )


def _fit_font(
    draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int, min_size: int
):
    """Largest font (<= start_size) whose rendered `text` width fits `max_width`.

    Font metrics differ across systems (Arial on Windows vs DejaVu in the Linux
    container — DejaVu is noticeably wider), so fixed size ratios overflow the
    plates on one platform. Measuring + shrinking keeps stamps inside the card
    everywhere.
    """
    size = max(min_size, start_size)
    while size > min_size:
        font = _try_font(size)
        if _text_width(draw, text, font) <= max_width:
            return font
        size -= max(1, size // 12)
    return _try_font(min_size)


def _band_chrome_bbox(
    frame_rgba: Image.Image, region: tuple[int, int, int, int]
) -> tuple[int, int, int, int]:
    """Opaque chrome bbox within a frame sub-rectangle (for plate-aware stamps)."""
    x0, y0, x1, y1 = region
    w, h = frame_rgba.size
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return region
    sub = frame_rgba.crop((x0, y0, x1, y1))
    alpha = sub.getchannel("A").point(lambda a: 255 if a >= 40 else 0)
    bb = alpha.getbbox()
    if not bb:
        return region
    return (x0 + bb[0], y0 + bb[1], x0 + bb[2], y0 + bb[3])


def _scrub_chrome_black_trails(
    rgb: Image.Image,
    *,
    protect: tuple[int, int, int, int] | None = None,
) -> Image.Image:
    """Remove near-black trail pixels on chrome (outside the photo window)."""
    out = rgb.convert("RGB")
    w, h = out.size
    px = out.load()
    if protect:
        px0, py0, px1, py1 = protect
    else:
        px0 = py0 = px1 = py1 = -1

    def in_window(x: int, y: int) -> bool:
        return px0 <= x < px1 and py0 <= y < py1

    for y in range(h):
        for x in range(w):
            if in_window(x, y):
                continue
            r, g, b = px[x, y]
            if r > 42 or g > 42 or b > 42:
                continue
            mx, mn = max(r, g, b), min(r, g, b)
            if mx - mn > 30:
                continue
            neigh: list[tuple[int, int, int]] = []
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and not in_window(nx, ny):
                    nr, ng, nb = px[nx, ny]
                    if (nr + ng + nb) // 3 > 58:
                        neigh.append((nr, ng, nb))
            if len(neigh) >= 2:
                sr = sum(c[0] for c in neigh) // len(neigh)
                sg = sum(c[1] for c in neigh) // len(neigh)
                sb = sum(c[2] for c in neigh) // len(neigh)
                px[x, y] = (sr, sg, sb)
    return out


def _stamp_tier_chrome(
    canvas: Image.Image,
    *,
    tier: int,
    world: str,
    name: str,
    tagline: str,
    chrome_bbox: tuple[int, int, int, int] | None = None,
    brand_plate: tuple[int, int, int, int] | None = None,
    bottom_plate: tuple[int, int, int, int] | None = None,
    footer_plate: tuple[int, int, int, int] | None = None,
    badge_plate: tuple[int, int, int, int] | None = None,
    stamp_brand: bool = True,
    stamp_badge_only: bool = False,
    badge_style: str = "stack",
    layout: StampLayout | None = None,
) -> None:
    """
    Reference-style plates (see LOOT ROOM CARDS examples):
      top-left  AOF LOOT
      top-right TIER N + world
      bottom    NAME + flavor

    Border animated cards: stamp_badge_only=True, badge_style='sunken' (tier digit + coord only).
    """
    draw = ImageDraw.Draw(canvas)
    w, h = canvas.size
    if chrome_bbox:
        x0, y0, x1, y1 = chrome_bbox
    else:
        x0, y0, x1, y1 = 0, 0, w, h
    cw, ch = max(1, x1 - x0), max(1, y1 - y0)

    tier_font = _try_font(max(12, ch // 30))
    flavor_font = _try_font(max(10, ch // 52))
    hub_font = _try_font(max(9, ch // 58))

    # top-left brand — blank-plate frames only; skip when frame bakes its own wordmark.
    if stamp_brand and not stamp_badge_only:
        show_hub = layout.show_hub if layout else True
        bh = 0
        if brand_plate and brand_plate[2] > brand_plate[0] + 20:
            px0, py0, px1, py1 = brand_plate
            pw, ph = px1 - px0, py1 - py0
            brand_start = max(
                layout.brand_min_font if layout else 10,
                int(ph * (0.30 if show_hub else 0.44)),
            )
            brand_max = int(pw * 0.88)
            brand_font = _fit_font(
                draw, "AOF LOOT", brand_max, brand_start, layout.brand_min_font if layout else 10
            )
            bw = _text_width(draw, "AOF LOOT", brand_font)
            bh = _text_height(draw, "AOF LOOT", brand_font)
            hub_h = _text_height(draw, "@aof_lootgod_bot", hub_font) if show_hub else 0
            gap_brand_hub = max(2, int(ph * 0.03)) if show_hub else 0
            block_h = bh + gap_brand_hub + hub_h
            brand_x = px0 + max(2, (pw - bw) // 2)
            brand_y = py0 + max(2, (ph - block_h) // 2)
        elif layout:
            brand_x = x0 + int(cw * layout.brand_x)
            brand_y = y0 + int(ch * layout.brand_y)
            brand_max = int(cw * layout.brand_max_w)
            brand_start = max(layout.brand_min_font, int(ch * layout.brand_font_h))
            brand_font = _fit_font(draw, "AOF LOOT", brand_max, brand_start, layout.brand_min_font)
            bb = draw.textbbox((0, 0), "AOF LOOT", font=brand_font)
            bh = bb[3] - bb[1]
        else:
            brand_x = x0 + int(cw * 0.05)
            brand_y = y0 + int(ch * 0.04)
            brand_font = _fit_font(draw, "AOF LOOT", int(cw * 0.48), max(20, ch // 13), 14)
            bb = draw.textbbox((0, 0), "AOF LOOT", font=brand_font)
            bh = bb[3] - bb[1]
            show_hub = True
        _draw_text_outlined(draw, (brand_x, brand_y), "AOF LOOT", font=brand_font, thin=True)

        if show_hub:
            hub = "@aof_lootgod_bot"
            if brand_plate and brand_plate[2] > brand_plate[0] + 20:
                gap = max(2, int((brand_plate[3] - brand_plate[1]) * 0.03))
                hub_y = brand_y + bh + gap
                hw = _text_width(draw, hub, hub_font)
                px0, _, px1, _ = brand_plate
                hub_x = px0 + max(2, (px1 - px0 - hw) // 2)
            else:
                hub_y = brand_y + max(12, bh)
                hub_x = brand_x
            _draw_text_outlined(
                draw,
                (hub_x, hub_y),
                hub,
                font=hub_font,
                fill=(180, 180, 180, 230),
                thin=True,
            )

    # top-right tier badge — text-only when a plate is detected; legacy green chip otherwise.
    world_s = (world or "").strip()
    if badge_plate and badge_plate[2] > badge_plate[0] + 20:
        if badge_style == "sunken":
            _draw_sunken_badge_plate(draw, plate=badge_plate, tier=tier, world_s=world_s)
        else:
            _draw_badge_plate_stack(
                draw, plate=badge_plate, tier=tier, world_s=world_s, ch=ch
            )
    elif not stamp_badge_only:
        tier_label = f"TIER {tier}"
        tw = _text_width(draw, tier_label, tier_font)
        badge_pad_x, badge_pad_y = 8, 5
        badge_h = max(18, int(ch * layout.badge_h)) + badge_pad_y if layout else max(20, ch // 22) + badge_pad_y
        if layout:
            bx1 = min(x0 + int(cw * layout.badge_x1), w - 4)
            by0 = y0 + int(ch * layout.badge_y0)
            bx0 = bx1 - tw - badge_pad_x * 2
            by1 = by0 + badge_h
        else:
            bx1 = min(x1 - int(cw * 0.05), w - max(6, int(cw * 0.02)))
            by0 = y0 + int(ch * 0.05)
            bx0 = bx1 - tw - badge_pad_x * 2
            by1 = by0 + badge_h
        draw.rounded_rectangle(
            (bx0, by0, bx1, by1),
            radius=6,
            fill=(10, 40, 18, 230),
            outline=(40, 220, 90, 255),
            width=2,
        )
        _draw_text_outlined(
            draw,
            (bx0 + badge_pad_x, by0 + badge_pad_y // 2),
            tier_label,
            font=tier_font,
            fill=(240, 255, 245, 255),
            thin=True,
        )
        if world_s:
            ww = _text_width(draw, world_s, hub_font)
            _draw_text_outlined(
                draw,
                (bx1 - ww, by1 + 4),
                world_s,
                font=hub_font,
                fill=(200, 255, 210, 240),
            )

    if stamp_badge_only:
        return

    # bottom name + flavor — name on the nameplate; tagline in footer_plate when set.
    name_u = (name or f"Tier {tier}").strip().upper() or f"TIER {tier}"
    name_start = max(16, int(ch * layout.name_font_h)) if layout else max(24, ch // 11)
    name_font = _fit_font(draw, name_u, int(cw * 0.86), name_start, 16)
    nw = _text_width(draw, name_u, name_font)
    nb = draw.textbbox((0, 0), name_u, font=name_font)
    nh = nb[3] - nb[1]
    tl = tagline.strip()[:56] if tagline else ""
    th = 0
    if tl:
        tb = draw.textbbox((0, 0), tl, font=flavor_font)
        th = tb[3] - tb[1]
    gap = max(8, ch // 52) if bottom_plate else max(4, ch // 80)
    block_h = nh + (gap + th if tl and not footer_plate else 0)
    if bottom_plate and bottom_plate[2] > bottom_plate[0] + 20:
        px0, py0, px1, py1 = bottom_plate
        pw, ph = px1 - px0, py1 - py0
        name_max = int(pw * 0.92)
        if nw > name_max:
            name_font = _fit_font(draw, name_u, name_max, name_start, 14)
            nw = _text_width(draw, name_u, name_font)
            nb = draw.textbbox((0, 0), name_u, font=name_font)
            nh = nb[3] - nb[1]
            block_h = nh + (gap + th if tl and not footer_plate else 0)
        nx = px0 + (pw - nw) // 2
        if footer_plate:
            by = py0 + (ph - nh) // 2
        else:
            by = py0 + (ph - block_h) // 2
    else:
        bottom_pad = max(10, ch // 24)
        by = max(y0, y1 - bottom_pad - block_h)
        nx = x0 + max(8, (cw - nw) // 2)
    _draw_text_outlined(draw, (nx, by), name_u, font=name_font, thin=True)
    if tl:
        lw = _text_width(draw, tl, flavor_font)
        if footer_plate and footer_plate[2] > footer_plate[0] + 20:
            fx0, fy0, fx1, fy1 = footer_plate
            fw, fh = fx1 - fx0, fy1 - fy0
            lx = fx0 + (fw - lw) // 2
            ly = fy0 + max(0, (fh - th) // 2)
        elif bottom_plate and bottom_plate[2] > bottom_plate[0] + 20:
            px0, _, px1, _ = bottom_plate
            pw = px1 - px0
            lx = px0 + (pw - lw) // 2
            ly = by + nh + gap
        else:
            lx = x0 + max(8, (cw - lw) // 2)
            ly = by + nh + gap
        _draw_text_outlined(
            draw,
            (lx, ly),
            tl,
            font=flavor_font,
            fill=(210, 210, 210, 240),
        )


def _bytes_to_center_jpeg(data: bytes) -> bytes | None:
    """Normalize loot media bytes to JPEG for the reveal window."""
    try:
        im = Image.open(io.BytesIO(data))
        im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=90, optimize=True)
        return buf.getvalue()
    except Exception:
        return None


def roll_reveal_rng(preview: dict | None, rng: random.Random | None = None) -> random.Random:
    if rng is not None:
        return rng
    seed_raw = (preview or {}).get("seed")
    media_ids = [
        int(m["id"]) for m in ((preview or {}).get("media") or []) if m.get("id") is not None
    ]
    mix = 0
    if seed_raw is not None:
        try:
            mix ^= int(seed_raw)
        except (TypeError, ValueError):
            pass
    for mid in media_ids:
        mix ^= int(mid) * 2654435761
    if mix:
        return random.Random(mix & 0xFFFFFFFF)
    return random.Random()


def _frame_layout_score(path: Path) -> float:
    """Prefer frames with real top/bottom chrome plates + true transparent window."""
    try:
        im = Image.open(path).convert("RGBA")
        if max(im.size) > 512:
            im = im.resize((512, 512), Image.Resampling.BILINEAR)
        a = im.getchannel("A")
        w, h = im.size
        top = a.crop((0, 0, w, max(1, h // 8)))
        bot = a.crop((0, h - max(1, h // 8), w, h))
        mid = a.crop((w // 4, h // 4, 3 * w // 4, 3 * h // 4))
        top_o = sum(1 for v in top.getdata() if v > 200) / max(1, top.size[0] * top.size[1])
        bot_o = sum(1 for v in bot.getdata() if v > 200) / max(1, bot.size[0] * bot.size[1])
        mid_o = sum(1 for v in mid.getdata() if v > 200) / max(1, mid.size[0] * mid.size[1])
        # true hole in the window is a strong positive signal (remove.bg plates)
        hole_bonus = 0.8 if mid_o < 0.15 else 0.0
        halo_penalty = _frame_chroma_halo_frac(path) * 4.0
        return float(top_o + bot_o - mid_o * 0.5 + hole_bonus - halo_penalty)
    except Exception:
        return 0.0


def pick_frame_path(rng: random.Random, frames: list[Path] | None = None) -> Path | None:
    """Bias toward layout-friendly borders (text plates), still random among top half."""
    frames = list(frames or list_reveal_frame_paths())
    if not frames:
        return None
    if len(frames) == 1:
        return frames[0]
    scored = sorted((( _frame_layout_score(p), p) for p in frames), key=lambda t: t[0], reverse=True)
    top_n = max(3, len(scored) // 2)
    pool = [p for _s, p in scored[:top_n]]
    return rng.choice(pool)


def _scrub_checker_to_black(
    rgb: Image.Image,
    *,
    protect: tuple[int, int, int, int] | None = None,
) -> Image.Image:
    """
    Paint leftover baked checker cells to solid black — only outside the art window.
    Never touch the center still (dark hair/skin would be destroyed).
    """
    out = rgb.convert("RGB")
    w, h = out.size
    px = out.load()
    means = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            means[y][x] = (r + g + b) // 3
    if protect:
        px0, py0, px1, py1 = protect
    else:
        px0 = py0 = px1 = py1 = -1
    for y in range(h):
        for x in range(w):
            if px0 <= x < px1 and py0 <= y < py1:
                continue
            r, g, b = px[x, y]
            mx, mn = max(r, g, b), min(r, g, b)
            mean = means[y][x]
            if mx - mn >= 22:
                continue
            if not (40 <= mean <= 230):
                continue
            neigh = []
            if x + 1 < w:
                neigh.append(means[y][x + 1])
            if y + 1 < h:
                neigh.append(means[y + 1][x])
            if x > 0:
                neigh.append(means[y][x - 1])
            if y > 0:
                neigh.append(means[y - 1][x])
            if any(abs(mean - nm) >= 16 for nm in neigh):
                px[x, y] = (0, 0, 0)
    return out


def compose_reveal_card(
    tier: int,
    *,
    rng: random.Random | None = None,
    size: int = 1024,
    stamp_chrome: bool = True,
    world: str | None = None,
    name: str | None = None,
    tagline: str | None = None,
    frame_path: Path | None = None,
    center_path: Path | None = None,
) -> bytes | None:
    """
    Build a unique reveal card: band center under punched frame, cropped tight to chrome.

    Returns opaque JPEG bytes (no alpha / no exterior checker margins).
    """
    rng = rng or random.Random()
    t = max(1, min(10, int(tier)))

    frames = list_reveal_frame_paths()
    centers = list_center_paths(t)
    if not frames and not centers:
        return None

    if not frames:
        path = center_path or (centers[0] if centers else None)
        if path is None:
            return None
        data = path.read_bytes()
        return data if data else None

    fp = frame_path or pick_frame_path(rng, frames)
    if fp is None:
        return None
    cp = center_path or (rng.choice(centers) if centers else None)

    frame = Image.open(fp).convert("RGBA")
    if frame.size != (size, size):
        frame = frame.resize((size, size), Image.Resampling.LANCZOS)
    frame = sanitize_frame_alpha(frame)
    # Gemini "bg removed" exports often fill holes with solid black (no alpha).
    mx, my = size // 2, size // 2
    mr, mg, mb, ma = frame.getpixel((mx, my))
    if ma > 200 and mr < 22 and mg < 22 and mb < 22:
        frame = key_near_black_to_alpha(frame)
    frame = sanitize_frame_alpha(frame)  # fast-path if now clean
    chrome_bbox = _solid_chrome_bbox(frame)

    # Opaque dark square — backdrop only; trimmed away after composite.
    canvas = Image.new("RGBA", (size, size), (8, 8, 10, 255))
    x0, y0, x1, y1 = _window_bbox(frame)
    win_w, win_h = max(1, x1 - x0), max(1, y1 - y0)

    if cp is not None:
        center = Image.open(cp).convert("RGB").convert("RGBA")
        fitted = _cover_resize(center, (win_w, win_h))
        r, g, b, _a = fitted.split()
        fitted = Image.merge("RGBA", (r, g, b, Image.new("L", fitted.size, 255)))
        canvas.paste(fitted, (x0, y0))
    else:
        ImageDraw.Draw(canvas).rectangle((x0, y0, x1 - 1, y1 - 1), fill=(28, 28, 32, 255))

    canvas.alpha_composite(frame)

    # Flatten to solid black RGB, scrub baked checker outside the art window, trim.
    base = Image.new("RGB", canvas.size, (0, 0, 0))
    base.paste(canvas.convert("RGBA"), mask=canvas.split()[-1])
    base = _scrub_checker_to_black(base, protect=(x0, y0, x1, y1))
    crop_ox, crop_oy = 0, 0
    cx0, cy0, cx1, cy1 = _solid_chrome_bbox(frame)
    if (cx1 - cx0) >= 64 and (cy1 - cy0) >= 64 and (cx1 - cx0) < int(size * 0.98):
        crop_ox, crop_oy = cx0, cy0
        base = base.crop((cx0, cy0, cx1, cy1))
    else:
        pad_x = max(24, int((x1 - x0) * 0.14))
        pad_y = max(24, int((y1 - y0) * 0.14))
        crop_ox = max(0, x0 - pad_x)
        crop_oy = max(0, y0 - pad_y)
        base = base.crop(
            (
                crop_ox,
                crop_oy,
                min(canvas.size[0], x1 + pad_x),
                min(canvas.size[1], y1 + pad_y),
            )
        )
    tx0, ty0, tx1, ty1 = _content_trim_bbox(base)
    if tx1 - tx0 >= 32 and ty1 - ty0 >= 32:
        crop_ox += tx0
        crop_oy += ty0
        base = base.crop((tx0, ty0, tx1, ty1))

    win_protect = (x0 - crop_ox, y0 - crop_oy, x1 - crop_ox, y1 - crop_oy)
    base = _scrub_chrome_black_trails(base, protect=win_protect)

    # Stamp AFTER all cropping so label positions are relative to the final card.
    if stamp_chrome:
        from app.services.loot_card_frame_styles import layout_for_frame

        try:
            from app.services.loot_tier_catalog import TIER_META

            meta = TIER_META.get(t) or {}
        except Exception:
            meta = {}
        stamp_layout = layout_for_frame(frame, path=fp)
        stamp_rgba = base.convert("RGBA")
        fw, fh = frame.size
        bottom_plate = _band_chrome_bbox(frame, (0, int(fh * 0.74), fw, fh))
        badge_plate = _band_chrome_bbox(frame, (int(fw * 0.50), 0, fw, int(fh * 0.24)))

        def _shift(bb: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
            return (bb[0] - crop_ox, bb[1] - crop_oy, bb[2] - crop_ox, bb[3] - crop_oy)

        sw, sh = stamp_rgba.size
        _stamp_tier_chrome(
            stamp_rgba,
            tier=t,
            world=world if world is not None else str(meta.get("world") or ""),
            name=name if name is not None else str(meta.get("name") or f"Tier {t}"),
            tagline=tagline if tagline is not None else str(meta.get("tagline") or ""),
            chrome_bbox=(0, 0, sw, sh),
            bottom_plate=_shift(bottom_plate),
            badge_plate=_shift(badge_plate),
            stamp_brand=fp.name.lower().startswith("mag-"),
            layout=stamp_layout,
        )
        base = _scrub_chrome_black_trails(stamp_rgba.convert("RGB"), protect=win_protect)
    # Telegram send_photo must get opaque bytes — no alpha channel, ever.
    if base.mode != "RGB":
        base = base.convert("RGB")
    buf = io.BytesIO()
    base.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()


def compose_reveal_border_layers(
    tier: int,
    *,
    rng: random.Random | None = None,
    size: int = 1024,
    world: str | None = None,
    name: str | None = None,
    tagline: str | None = None,
    frame_path: Path | None = None,
    center_path: Path | None = None,
    center_jpeg: bytes | None = None,
    border_open: Path | None = None,
    border_stasis: Path | None = None,
    border_clip: Path | None = None,
    preview: dict | None = None,
) -> tuple[bytes, bytes] | None:
    """
    Layers for animated border reveal (no static frame chrome):
      - center JPEG: rolled loot still in the border window
      - stamp PNG: RGBA text-only overlay aligned to border plates
    """
    from app.services.loot_border_plates import plates_for_border_clip
    from app.services.loot_border_profiles import frac_rect_to_px, profile_for_border
    from app.services.loot_card_frame_styles import StampLayout

    rng = roll_reveal_rng(preview, rng)
    t = max(1, min(10, int(tier)))
    clip = border_clip or border_open or border_stasis
    profile = profile_for_border(clip)
    stamp_layout = profile.stamp_layout if profile else None
    stamp_brand = profile.stamp_brand if profile else True

    if clip and clip.is_file():
        geom = plates_for_border_clip(clip)
        x0, y0, x1, y1 = frac_rect_to_px(geom["window"], size)
        brand_plate = frac_rect_to_px(geom["brand_plate"], size)
        badge_plate = frac_rect_to_px(geom["badge_plate"], size)
        bottom_plate = frac_rect_to_px(geom["bottom_plate"], size)
        footer_plate = None
        if profile and profile.footer_plate:
            footer_plate = frac_rect_to_px(profile.footer_plate, size)
        elif geom.get("bottom_plate"):
            bx0, _, bx1, by1 = geom["bottom_plate"]
            footer_plate = frac_rect_to_px((bx0, by1, bx1, min(1.0, by1 + 0.06)), size)
        if stamp_layout is None:
            stamp_layout = StampLayout(
                style_id="auto",
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
    elif profile:
        x0, y0, x1, y1 = frac_rect_to_px(profile.window, size)
        brand_plate = frac_rect_to_px(profile.brand_plate, size)
        badge_plate = frac_rect_to_px(profile.badge_plate, size)
        bottom_plate = frac_rect_to_px(profile.bottom_plate, size)
        footer_plate = (
            frac_rect_to_px(profile.footer_plate, size) if profile.footer_plate else None
        )
    else:
        frames = list_reveal_frame_paths()
        if not frames:
            return None
        fp = frame_path or pick_frame_path(rng, frames)
        if fp is None:
            return None
        frame = Image.open(fp).convert("RGBA")
        if frame.size != (size, size):
            frame = frame.resize((size, size), Image.Resampling.LANCZOS)
        frame = sanitize_frame_alpha(frame)
        mx, my = size // 2, size // 2
        mr, mg, mb, ma = frame.getpixel((mx, my))
        if ma > 200 and mr < 22 and mg < 22 and mb < 22:
            frame = key_near_black_to_alpha(frame)
        frame = sanitize_frame_alpha(frame)
        x0, y0, x1, y1 = _window_bbox(frame)
        fw, fh = frame.size
        bottom_plate = _band_chrome_bbox(frame, (0, int(fh * 0.74), fw, fh))
        badge_plate = _band_chrome_bbox(frame, (int(fw * 0.50), 0, fw, int(fh * 0.24)))
        brand_plate = None
        footer_plate = None
        from app.services.loot_card_frame_styles import layout_for_frame

        stamp_layout = layout_for_frame(frame, path=fp)
        stamp_brand = fp.name.lower().startswith("mag-")

    centers = list_center_paths(t)
    cp = center_path
    if cp is None and not center_jpeg and centers:
        cp = centers[rng.randrange(len(centers))]

    win_w, win_h = max(1, x1 - x0), max(1, y1 - y0)
    # Exact window fit — no bleed (bleed caused dark fringe under inner chrome).
    canvas = Image.new("RGB", (size, size), (0, 0, 0))
    if center_jpeg:
        center = Image.open(io.BytesIO(center_jpeg)).convert("RGB")
        fitted = _cover_resize(center.convert("RGBA"), (win_w, win_h))
        canvas.paste(fitted.convert("RGB"), (x0, y0))
    elif cp is not None:
        center = Image.open(cp).convert("RGB")
        fitted = _cover_resize(center.convert("RGBA"), (win_w, win_h))
        canvas.paste(fitted.convert("RGB"), (x0, y0))
    else:
        ImageDraw.Draw(canvas).rectangle((x0, y0, x1 - 1, y1 - 1), fill=(28, 28, 32))

    center_jpeg = io.BytesIO()
    canvas.save(center_jpeg, format="JPEG", quality=92, optimize=True)

    stamp_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    try:
        from app.services.loot_tier_catalog import TIER_META

        meta = TIER_META.get(t) or {}
    except Exception:
        meta = {}
    _stamp_tier_chrome(
        stamp_layer,
        tier=t,
        world=world if world is not None else str(meta.get("world") or ""),
        name=name if name is not None else str(meta.get("name") or f"Tier {t}"),
        tagline=tagline if tagline is not None else str(meta.get("tagline") or ""),
        chrome_bbox=(0, 0, size, size),
        brand_plate=brand_plate,
        bottom_plate=bottom_plate,
        footer_plate=footer_plate,
        badge_plate=badge_plate,
        stamp_brand=False,
        stamp_badge_only=True,
        badge_style="sunken",
        layout=stamp_layout,
    )
    stamp_png = io.BytesIO()
    stamp_layer.save(stamp_png, format="PNG")
    return center_jpeg.getvalue(), stamp_png.getvalue()


def build_reveal_card_png(
    tier: int,
    *,
    rng: random.Random | None = None,
    preview: dict | None = None,
) -> tuple[bytes | None, str]:
    """
    Preferred entry for delivery.

    Returns (jpeg_bytes_or_none, note).
    Falls back to static tier-{n}.png when composite assets are missing.
    """
    t = max(1, min(10, int(tier)))
    meta_world = meta_name = meta_tag = None
    if preview:
        meta_world = preview.get("world_label") or preview.get("world")
        meta_name = preview.get("tier_name") or preview.get("name")
        meta_tag = preview.get("tagline")

    frames = list_reveal_frame_paths()
    centers = list_center_paths(t)
    pool = reveal_frame_pool_kind()
    if frames:
        data = compose_reveal_card(
            t,
            rng=rng,
            world=str(meta_world) if meta_world else None,
            name=str(meta_name) if meta_name else None,
            tagline=str(meta_tag) if meta_tag else None,
        )
        if data:
            band = center_band_for_tier(t)
            return (
                data,
                f"composite pool={pool} frames={len(frames)} centers={len(centers)} "
                f"band={band} tier={t}",
            )

    legacy = resolve_tier_card_path(t)
    if legacy is not None:
        try:
            from app.services.loot_border_reveal import loot_border_reveal_enabled

            if loot_border_reveal_enabled():
                return None, "static_blocked:border_reveal"
        except Exception:
            pass
        return legacy.read_bytes(), f"static:{legacy.name}"
    return None, "missing"


def build_reveal_card_mp4(
    tier: int,
    *,
    rng: random.Random | None = None,
    preview: dict | None = None,
) -> tuple[bytes | None, str]:
    """
    Animated reveal: single border clip (open+sustain baked in) or background loop fallback.

    Returns (mp4_bytes_or_none, note). Requires TBCC_LOOT_REVEAL_VIDEO=1 and ffmpeg.
    """
    t = max(1, min(10, int(tier)))
    meta_world = meta_name = meta_tag = None
    center_jpeg = None
    if preview:
        meta_world = preview.get("world_label") or preview.get("world")
        meta_name = preview.get("tier_name") or preview.get("name")
        meta_tag = preview.get("tagline")
        raw_center = preview.get("center_jpeg")
        if isinstance(raw_center, (bytes, bytearray)) and raw_center:
            center_jpeg = bytes(raw_center)
        else:
            raw_b64 = preview.get("center_jpeg_b64")
            if isinstance(raw_b64, str) and raw_b64.strip():
                import base64

                center_jpeg = base64.b64decode(raw_b64)

    rng = roll_reveal_rng(preview, rng)

    from app.services.loot_border_reveal import loot_border_reveal_enabled

    if loot_border_reveal_enabled():
        from app.services.loot_border_reveal import compose_border_reveal_mp4, pick_border_clip
        from app.services.loot_reveal_video import reveal_video_size

        dim = reveal_video_size()
        clip = pick_border_clip(rng)
        if clip:
            layers = compose_reveal_border_layers(
                t,
                rng=rng,
                size=dim,
                world=str(meta_world) if meta_world else None,
                name=str(meta_name) if meta_name else None,
                tagline=str(meta_tag) if meta_tag else None,
                border_clip=clip,
                center_jpeg=center_jpeg,
                preview=preview,
            )
            if layers:
                center_jpeg, stamp_png = layers
                mp4, vnote = compose_border_reveal_mp4(
                    center_jpeg, stamp_png, rng=rng, border_clip=clip, size=dim
                )
                if mp4:
                    return mp4, vnote

    card_bytes, card_note = build_reveal_card_png(tier, rng=rng, preview=preview)
    if not card_bytes:
        return None, "no_card"
    from app.services.loot_reveal_video import compose_reveal_card_mp4

    mp4, vnote = compose_reveal_card_mp4(card_bytes, rng=rng)
    if not mp4:
        return None, f"{vnote} card={card_note}"
    return mp4, f"{vnote} card={card_note}"


def build_reveal_border_still_jpeg(
    tier: int,
    *,
    rng: random.Random | None = None,
    preview: dict | None = None,
    center_jpeg: bytes | None = None,
) -> tuple[bytes | None, str]:
    """Static border card fallback when animated reveal encode fails."""
    t = max(1, min(10, int(tier)))
    meta_world = meta_name = meta_tag = None
    if preview:
        meta_world = preview.get("world_label") or preview.get("world")
        meta_name = preview.get("tier_name") or preview.get("name")
        meta_tag = preview.get("tagline")
        raw_center = preview.get("center_jpeg")
        if center_jpeg is None and isinstance(raw_center, (bytes, bytearray)) and raw_center:
            center_jpeg = bytes(raw_center)

    rng = roll_reveal_rng(preview, rng)

    from app.services.loot_border_reveal import (
        compose_border_reveal_still_jpeg,
        loot_border_reveal_enabled,
        pick_border_clip,
    )
    from app.services.loot_reveal_video import reveal_video_size

    if not loot_border_reveal_enabled():
        return None, "disabled"

    dim = reveal_video_size()
    clip = pick_border_clip(rng)
    if not clip:
        return None, "no_border_clips"
    layers = compose_reveal_border_layers(
        t,
        rng=rng,
        size=dim,
        world=str(meta_world) if meta_world else None,
        name=str(meta_name) if meta_name else None,
        tagline=str(meta_tag) if meta_tag else None,
        border_clip=clip,
        center_jpeg=center_jpeg,
        preview=preview,
    )
    if not layers:
        return None, "no_layers"
    center_jpeg, stamp_png = layers
    still = compose_border_reveal_still_jpeg(center_jpeg, stamp_png, clip, size=dim)
    if not still:
        return None, f"still_failed:clip={clip.name}"
    return still, f"border still clip={clip.name}"
