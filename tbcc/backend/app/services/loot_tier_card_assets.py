"""Resolve / compose loot reveal cards: transparent frame over band center art."""

from __future__ import annotations

import io
import os
import random
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

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


def list_reveal_frame_paths() -> list[Path]:
    """Frames to actually composite from: the curated clean/ pool when present,
    else the raw top-level pool (back-compat / fresh checkouts without clean/)."""
    clean = list_clean_frame_paths()
    return clean if clean else list_frame_paths()


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


def _draw_text_outlined(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int] = (245, 245, 245, 255),
    outline: tuple[int, int, int, int] = (0, 0, 0, 200),
) -> None:
    x, y = xy
    for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1), (-1, -1)):
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


def _stamp_tier_chrome(
    canvas: Image.Image,
    *,
    tier: int,
    world: str,
    name: str,
    tagline: str,
    chrome_bbox: tuple[int, int, int, int] | None = None,
) -> None:
    """
    Reference-style plates (see LOOT ROOM CARDS examples):
      top-left  AOF LOOT
      top-right TIER N + world
      bottom    NAME + flavor
    """
    draw = ImageDraw.Draw(canvas)
    w, h = canvas.size
    if chrome_bbox:
        x0, y0, x1, y1 = chrome_bbox
    else:
        x0, y0, x1, y1 = 0, 0, w, h
    cw, ch = max(1, x1 - x0), max(1, y1 - y0)

    tier_font = _try_font(max(14, ch // 26))
    flavor_font = _try_font(max(12, ch // 40))
    hub_font = _try_font(max(10, ch // 52))

    # top-left brand — fit within the left ~48% so it never runs into the badge.
    brand_x = x0 + int(cw * 0.05)
    brand_y = y0 + int(ch * 0.04)
    brand_font = _fit_font(draw, "AOF LOOT", int(cw * 0.48), max(20, ch // 13), 14)
    _draw_text_outlined(draw, (brand_x, brand_y), "AOF LOOT", font=brand_font)

    hub = "t.me/aofmainhub"
    hub_y = brand_y + max(18, ch // 18)
    _draw_text_outlined(
        draw,
        (brand_x, hub_y),
        hub,
        font=hub_font,
        fill=(180, 180, 180, 230),
    )

    # top-right tier badge
    world_s = (world or "").strip()
    tier_label = f"TIER {tier}"
    tw = _text_width(draw, tier_label, tier_font)
    badge_pad_x, badge_pad_y = 10, 6
    # Keep the badge fully inside the card's right edge (was clipping on Linux).
    bx1 = min(x1 - int(cw * 0.05), w - max(6, int(cw * 0.02)))
    by0 = y0 + int(ch * 0.05)
    bx0 = bx1 - tw - badge_pad_x * 2
    by1 = by0 + max(22, ch // 20) + badge_pad_y
    # neon-ish plate
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

    # bottom name + flavor — stacked and bottom-anchored so the tagline never
    # lands on the name's descenders (they used to overlap).
    name_u = (name or f"Tier {tier}").strip().upper() or f"TIER {tier}"
    name_font = _fit_font(draw, name_u, int(cw * 0.86), max(24, ch // 11), 16)
    nw = _text_width(draw, name_u, name_font)
    nb = draw.textbbox((0, 0), name_u, font=name_font)
    nh = nb[3] - nb[1]
    tl = tagline.strip()[:56] if tagline else ""
    th = 0
    if tl:
        tb = draw.textbbox((0, 0), tl, font=flavor_font)
        th = tb[3] - tb[1]
    gap = max(4, ch // 80)
    block_h = nh + (gap + th if tl else 0)
    bottom_pad = max(10, ch // 24)
    by = max(y0, y1 - bottom_pad - block_h)
    nx = x0 + max(8, (cw - nw) // 2)
    _draw_text_outlined(draw, (nx, by), name_u, font=name_font)
    if tl:
        lw = _text_width(draw, tl, flavor_font)
        lx = x0 + max(8, (cw - lw) // 2)
        _draw_text_outlined(
            draw,
            (lx, by + nh + gap),
            tl,
            font=flavor_font,
            fill=(210, 210, 210, 240),
        )


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
        return float(top_o + bot_o - mid_o * 0.5 + hole_bonus)
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

    if stamp_chrome:
        try:
            from app.services.loot_tier_catalog import TIER_META

            meta = TIER_META.get(t) or {}
        except Exception:
            meta = {}
        _stamp_tier_chrome(
            canvas,
            tier=t,
            world=world if world is not None else str(meta.get("world") or ""),
            name=name if name is not None else str(meta.get("name") or f"Tier {t}"),
            tagline=tagline if tagline is not None else str(meta.get("tagline") or ""),
            chrome_bbox=chrome_bbox,
        )

    # Flatten to solid black RGB, scrub baked checker outside the art window, trim.
    base = Image.new("RGB", canvas.size, (0, 0, 0))
    base.paste(canvas.convert("RGBA"), mask=canvas.split()[-1])
    base = _scrub_checker_to_black(base, protect=(x0, y0, x1, y1))
    cx0, cy0, cx1, cy1 = _solid_chrome_bbox(frame)
    if (cx1 - cx0) >= 64 and (cy1 - cy0) >= 64 and (cx1 - cx0) < int(size * 0.98):
        base = base.crop((cx0, cy0, cx1, cy1))
    else:
        pad_x = max(24, int((x1 - x0) * 0.14))
        pad_y = max(24, int((y1 - y0) * 0.14))
        base = base.crop(
            (
                max(0, x0 - pad_x),
                max(0, y0 - pad_y),
                min(canvas.size[0], x1 + pad_x),
                min(canvas.size[1], y1 + pad_y),
            )
        )
    tx0, ty0, tx1, ty1 = _content_trim_bbox(base)
    if tx1 - tx0 >= 32 and ty1 - ty0 >= 32:
        base = base.crop((tx0, ty0, tx1, ty1))
    # Telegram send_photo must get opaque bytes — no alpha channel, ever.
    if base.mode != "RGB":
        base = base.convert("RGB")
    buf = io.BytesIO()
    base.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()


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
    band = center_band_for_tier(t)
    pool = "clean" if list_clean_frame_paths() else "raw"
    if frames:
        data = compose_reveal_card(
            t,
            rng=rng,
            world=str(meta_world) if meta_world else None,
            name=str(meta_name) if meta_name else None,
            tagline=str(meta_tag) if meta_tag else None,
        )
        if data:
            return (
                data,
                f"composite pool={pool} frames={len(frames)} centers={len(centers)} "
                f"band={band} tier={t}",
            )

    legacy = resolve_tier_card_path(t)
    if legacy is not None:
        return legacy.read_bytes(), f"static:{legacy.name}"
    return None, "missing"
