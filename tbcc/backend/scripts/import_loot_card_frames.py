"""
Import Gemini transparent-border exports into loot_tier_cards/frames/.

Handles:
  - real alpha holes
  - chroma-green (#00FF00-ish) windows
  - baked checkerboard "fake transparency"
  - multi-frame spritesheets (grid of cards)

Usage:
  py -3.13 scripts/import_loot_card_frames.py
  py -3.13 scripts/import_loot_card_frames.py --src "D:\\path\\to\\borders"
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "app" / "data" / "loot_tier_cards"
DEFAULT_SRC = Path(
    r"C:\Users\ianmp\Downloads\tbcc\AOF NETWORK\AOF RESOURCES (ZIPS)\AOF LOGOS\_transparent border_gemini"
)


def _is_green(r: np.ndarray, g: np.ndarray, b: np.ndarray) -> np.ndarray:
    r16, g16, b16 = r.astype(np.int16), g.astype(np.int16), b.astype(np.int16)
    return ((g16 > 180) & (r16 < 100) & (b16 < 100)) | (
        (g16 > 160) & (g16 > r16 + 50) & (g16 > b16 + 50)
    )


def _is_checkerish(r: np.ndarray, g: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Gemini often bakes Photoshop-style grey checker into RGB (alpha=255)."""
    mx = np.maximum(np.maximum(r, g), b).astype(np.int16)
    mn = np.minimum(np.minimum(r, g), b).astype(np.int16)
    chroma = mx - mn
    mean = (r.astype(np.int16) + g.astype(np.int16) + b.astype(np.int16)) // 3
    neutral = chroma < 28
    # light + dark cells (Gemini uses both bright and muted checkers)
    light = neutral & (mean >= 155)
    dark = neutral & (mean >= 60) & (mean < 155)
    bri = mean
    shift = np.zeros_like(bri, dtype=bool)
    shift[:, 1:] |= np.abs(bri[:, 1:].astype(np.int16) - bri[:, :-1].astype(np.int16)) > 18
    shift[1:, :] |= np.abs(bri[1:, :].astype(np.int16) - bri[:-1, :].astype(np.int16)) > 18
    return (light | dark) & shift


def hole_candidate(rgba: np.ndarray) -> np.ndarray:
    a = rgba[:, :, 3]
    r, g, b = rgba[:, :, 0], rgba[:, :, 1], rgba[:, :, 2]
    return (a < 40) | _is_green(r, g, b) | _is_checkerish(r, g, b)


def solid_mask(rgba: np.ndarray) -> np.ndarray:
    """Chrome / metal pixels that make up the actual border."""
    return ~hole_candidate(rgba)


def _components(mask: np.ndarray, min_area: int) -> list[tuple[int, int, int, int]]:
    """Return bboxes (x0,y0,x1,y1) for connected True components above min_area."""
    h, w = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    boxes: list[tuple[int, int, int, int, int]] = []
    ys, xs = np.where(mask)
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        if visited[y0, x0]:
            continue
        stack = [(y0, x0)]
        visited[y0, x0] = True
        minx = maxx = x0
        miny = maxy = y0
        area = 0
        while stack:
            y, x = stack.pop()
            area += 1
            if x < minx:
                minx = x
            if x > maxx:
                maxx = x
            if y < miny:
                miny = y
            if y > maxy:
                maxy = y
            for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    stack.append((ny, nx))
        if area >= min_area:
            boxes.append((area, minx, miny, maxx, maxy))
    boxes.sort(key=lambda t: (-t[0], t[2], t[1]))
    return [(a, b, c, d) for _, a, b, c, d in boxes]


def _work_scale(im: Image.Image, max_side: int = 900) -> tuple[Image.Image, float]:
    w, h = im.size
    side = max(w, h)
    if side <= max_side:
        return im, 1.0
    scale = max_side / side
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    return im.resize((nw, nh), Image.Resampling.BILINEAR), scale


def _run_count(mask_1d: np.ndarray) -> int:
    """Number of contiguous True runs in a 1D boolean mask."""
    if mask_1d.size == 0:
        return 0
    # pad False ends
    m = np.concatenate([[False], mask_1d, [False]])
    return int(np.sum((~m[:-1]) & m[1:]))


def _gutter_lines_from_islands(solid: np.ndarray, axis: int) -> list[int]:
    """
    Find gutters between cards: lines where chrome island count drops to ~0
    while neighboring bands have multiple islands (or thick chrome).
    axis=0 → horizontal gutters (vary y); axis=1 → vertical gutters (vary x).
    """
    h, w = solid.shape
    if axis == 0:
        island = np.array([_run_count(solid[y]) for y in range(h)], dtype=np.int16)
        dens = solid.mean(axis=1)
        n = h
    else:
        island = np.array([_run_count(solid[:, x]) for x in range(w)], dtype=np.int16)
        dens = solid.mean(axis=0)
        n = w

    # smooth a little
    ker = np.ones(5) / 5.0
    island_s = np.convolve(island.astype(np.float64), ker, mode="same")
    dens_s = np.convolve(dens, ker, mode="same")

    # gutter candidate: few islands AND low-ish density
    gutter = (island_s < 0.75) & (dens_s < 0.55)
    lines: list[int] = []
    i = 0
    while i < n:
        if not gutter[i]:
            i += 1
            continue
        j = i
        while j < n and gutter[j]:
            j += 1
        if (j - i) >= 3:
            mid = (i + j) // 2
            # require that nearby bands look like card rows (more islands)
            lo = max(0, mid - max(15, n // 20))
            hi = min(n, mid + max(15, n // 20))
            neighbor = float(np.max(island_s[lo:hi])) if hi > lo else 0.0
            if neighbor >= 1.5 and mid > int(n * 0.05) and mid < int(n * 0.95):
                lines.append(mid)
        i = j
    return lines


def split_by_projection(im: Image.Image) -> list[Image.Image]:
    small, scale = _work_scale(im)
    rgba = np.array(small.convert("RGBA"))
    solid = solid_mask(rgba)
    row_lines = _gutter_lines_from_islands(solid, axis=0)
    col_lines = _gutter_lines_from_islands(solid, axis=1)
    if not row_lines and not col_lines:
        return []
    h, w = solid.shape
    ys = [0] + row_lines + [h]
    xs = [0] + col_lines + [w]

    def _unique(vals: list[int], min_gap: int) -> list[int]:
        out: list[int] = []
        for v in vals:
            if not out or v - out[-1] >= min_gap:
                out.append(v)
        return out

    ys = _unique(ys, min_gap=max(24, h // 14))
    xs = _unique(xs, min_gap=max(24, w // 14))
    n_cells = (len(ys) - 1) * (len(xs) - 1)
    if n_cells < 2 or n_cells > 24:
        return []

    crops: list[Image.Image] = []
    for yi in range(len(ys) - 1):
        for xi in range(len(xs) - 1):
            y0, y1 = ys[yi], ys[yi + 1]
            x0, x1 = xs[xi], xs[xi + 1]
            bw, bh = x1 - x0, y1 - y0
            if bw < 50 or bh < 50:
                continue
            aspect = bw / max(1, bh)
            if aspect < 0.55 or aspect > 1.9:
                continue
            cell_solid = float(solid[y0:y1, x0:x1].mean())
            if cell_solid < 0.15:
                continue
            fx0 = max(0, int(x0 / scale))
            fy0 = max(0, int(y0 / scale))
            fx1 = min(im.size[0], int(x1 / scale) + 1)
            fy1 = min(im.size[1], int(y1 / scale) + 1)
            crops.append(im.crop((fx0, fy0, fx1, fy1)))
    return crops if 2 <= len(crops) <= 24 else []


def _cell_looks_like_card(rgba_cell: np.ndarray) -> float:
    """Score 0..1 whether a crop looks like a single card frame."""
    h, w = rgba_cell.shape[:2]
    if h < 40 or w < 40:
        return 0.0
    solid = solid_mask(rgba_cell)
    hole = hole_candidate(rgba_cell)
    # border ring: solid near edges, hole near center
    edge = np.zeros_like(solid)
    t = max(2, min(h, w) // 12)
    edge[:t, :] = True
    edge[-t:, :] = True
    edge[:, :t] = True
    edge[:, -t:] = True
    cy0, cy1 = int(h * 0.3), int(h * 0.7)
    cx0, cx1 = int(w * 0.3), int(w * 0.7)
    center = hole[cy0:cy1, cx0:cx1]
    edge_solid = float(solid[edge].mean()) if edge.any() else 0.0
    center_hole = float(center.mean()) if center.size else 0.0
    # reject cells that are almost entirely hole (gutters) or entirely solid
    solid_frac = float(solid.mean())
    if solid_frac < 0.08 or solid_frac > 0.95:
        return 0.0
    return 0.55 * edge_solid + 0.45 * center_hole


def split_uniform_grid(im: Image.Image) -> list[Image.Image]:
    """Try common Gemini sheet layouts (3x3, 2x4, 2x5, …) by equal tiling."""
    small, scale = _work_scale(im, max_side=700)
    rgba = np.array(small.convert("RGBA"))
    h, w = rgba.shape[:2]
    best: list[Image.Image] = []
    best_score = 0.0
    for rows, cols in ((3, 3), (2, 4), (2, 5), (3, 4), (4, 2), (1, 5), (2, 3)):
        scores = []
        cells = []
        for r in range(rows):
            for c in range(cols):
                y0 = int(r * h / rows)
                y1 = int((r + 1) * h / rows)
                x0 = int(c * w / cols)
                x1 = int((c + 1) * w / cols)
                # inset slightly to avoid gutter bleed
                pad_y = max(1, (y1 - y0) // 30)
                pad_x = max(1, (x1 - x0) // 30)
                cell = rgba[y0 + pad_y : y1 - pad_y, x0 + pad_x : x1 - pad_x]
                sc = _cell_looks_like_card(cell)
                scores.append(sc)
                fx0 = max(0, int((x0 + pad_x) / scale))
                fy0 = max(0, int((y0 + pad_y) / scale))
                fx1 = min(im.size[0], int((x1 - pad_x) / scale))
                fy1 = min(im.size[1], int((y1 - pad_y) / scale))
                cells.append(im.crop((fx0, fy0, fx1, fy1)))
        if not scores:
            continue
        mean_sc = float(np.mean(scores))
        # require most cells to look like cards
        good = sum(1 for s in scores if s >= 0.28)
        if good < max(2, int(0.6 * rows * cols)):
            continue
        if mean_sc > best_score:
            best_score = mean_sc
            best = cells
    return best if best_score >= 0.30 else []


def _grid_cell_scores(rgba: np.ndarray, rows: int, cols: int) -> list[float]:
    h, w = rgba.shape[:2]
    scores: list[float] = []
    for r in range(rows):
        for c in range(cols):
            y0 = int(r * h / rows)
            y1 = int((r + 1) * h / rows)
            x0 = int(c * w / cols)
            x1 = int((c + 1) * w / cols)
            pad_y = max(1, (y1 - y0) // 30)
            pad_x = max(1, (x1 - x0) // 30)
            cell = rgba[y0 + pad_y : y1 - pad_y, x0 + pad_x : x1 - pad_x]
            scores.append(_cell_looks_like_card(cell))
    return scores


def count_interior_holes(rgba: np.ndarray) -> int:
    hole = hole_candidate(rgba)
    h_img = Image.fromarray((hole.astype(np.uint8) * 255), mode="L")
    h_img = h_img.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    hole = np.array(h_img) > 127
    h, w = hole.shape
    boxes = _components(hole, min_area=int(h * w * 0.004))
    n = 0
    for x0, y0, x1, y1 in boxes:
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        touches = x0 <= 1 or y0 <= 1 or x1 >= w - 2 or y1 >= h - 2
        if touches and bw > w * 0.7 and bh > h * 0.7:
            continue
        n += 1
    return n


def split_cards(im: Image.Image) -> list[Image.Image]:
    """
    Split spritesheets into per-card crops.
    Order: green windows → multi-hole grid → projection → solid → single.
    """
    small, scale = _work_scale(im)
    rgba = np.array(small.convert("RGBA"))
    h, w = rgba.shape[:2]

    # 1) Distinct green windows
    r, g, b = rgba[:, :, 0], rgba[:, :, 1], rgba[:, :, 2]
    green = _is_green(r, g, b)
    g_img = Image.fromarray((green.astype(np.uint8) * 255), mode="L")
    g_img = g_img.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(3))
    green = np.array(g_img) > 127
    green_boxes = _components(green, min_area=int(h * w * 0.008))
    if 2 <= len(green_boxes) <= 16:
        expanded = []
        for x0, y0, x1, y1 in green_boxes:
            bw, bh = x1 - x0 + 1, y1 - y0 + 1
            pad = int(0.28 * max(bw, bh))
            expanded.append(
                (
                    max(0, x0 - pad),
                    max(0, y0 - pad),
                    min(w - 1, x1 + pad),
                    min(h - 1, y1 + pad),
                )
            )
        crops = _boxes_to_crops(im, expanded, scale)
        if 2 <= len(crops) <= 16:
            return crops

    # 2) Multiple interior holes ⇒ spritesheet → uniform grid
    n_holes = count_interior_holes(rgba)
    if n_holes >= 2:
        grid = split_uniform_grid(im)
        if len(grid) >= 2:
            return grid

    # 3) Projection / island gutters
    proj = split_by_projection(im)
    if len(proj) >= 2:
        return proj

    # 4) Solid chrome blobs
    solid = solid_mask(rgba)
    s_img = Image.fromarray((solid.astype(np.uint8) * 255), mode="L")
    s_img = s_img.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    solid = np.array(s_img) > 127
    boxes = _components(solid, min_area=int(h * w * 0.008))
    crops = _boxes_to_crops(im, boxes, scale)
    if 2 <= len(crops) <= 16:
        return crops

    return [im]


def _boxes_to_crops(
    im: Image.Image, boxes: list[tuple[int, int, int, int]], scale: float
) -> list[Image.Image]:
    crops: list[Image.Image] = []
    for x0, y0, x1, y1 in boxes:
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        if bw < 40 or bh < 40:
            continue
        aspect = bw / max(1, bh)
        if aspect < 0.55 or aspect > 1.85:
            continue
        pad = int(0.04 * max(bw, bh))
        fx0 = max(0, int((x0 - pad) / scale))
        fy0 = max(0, int((y0 - pad) / scale))
        fx1 = min(im.size[0], int((x1 + pad) / scale) + 1)
        fy1 = min(im.size[1], int((y1 + pad) / scale) + 1)
        crops.append(im.crop((fx0, fy0, fx1, fy1)))
    return crops


def punch_window(im: Image.Image) -> Image.Image:
    """Force card window (green/checker/alpha) to real alpha=0; keep chrome opaque."""
    rgba = np.array(im.convert("RGBA"))
    hole = hole_candidate(rgba)
    solid = ~hole

    # Interior hole = hole pixels that are inside the chrome bbox and not the outer void.
    ys, xs = np.where(solid)
    if len(xs) == 0:
        # nothing solid — treat all holes as transparent and return
        rgba[hole, 3] = 0
        return Image.fromarray(rgba, "RGBA")

    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    # shrink inward so we don't clear the chrome ring itself
    inset_x = max(2, int((x1 - x0) * 0.08))
    inset_y = max(2, int((y1 - y0) * 0.08))
    ix0, ix1 = x0 + inset_x, x1 - inset_x
    iy0, iy1 = y0 + inset_y, y1 - inset_y

    window = np.zeros_like(hole, dtype=bool)
    if ix1 > ix0 and iy1 > iy0:
        inner = hole[iy0:iy1, ix0:ix1]
        window[iy0:iy1, ix0:ix1] = inner

        # Also flood from center if center is a hole candidate
        cy, cx = (iy0 + iy1) // 2, (ix0 + ix1) // 2
        if hole[cy, cx]:
            # flood fill constrained to inner rect
            h, w = hole.shape
            vis = np.zeros_like(hole, dtype=bool)
            stack = [(cy, cx)]
            vis[cy, cx] = True
            while stack:
                y, x = stack.pop()
                window[y, x] = True
                for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    ny, nx = y + dy, x + dx
                    if iy0 <= ny < iy1 and ix0 <= nx < ix1 and hole[ny, nx] and not vis[ny, nx]:
                        vis[ny, nx] = True
                        stack.append((ny, nx))

    # Soften window edge
    m_img = Image.fromarray((window.astype(np.uint8) * 255), mode="L")
    m_img = m_img.filter(ImageFilter.MaxFilter(3))
    window = np.array(m_img) > 127

    rgba[window, 3] = 0
    # kill leftover green in window
    r, g, b = rgba[:, :, 0], rgba[:, :, 1], rgba[:, :, 2]
    rgba[_is_green(r, g, b), 3] = 0

    # outer void (outside chrome bbox) → transparent too
    outer = np.ones(hole.shape, dtype=bool)
    outer[y0 : y1 + 1, x0 : x1 + 1] = False
    rgba[outer & hole, 3] = 0

    return Image.fromarray(rgba, "RGBA")


def normalize_frame(im: Image.Image, size: int = 1024) -> Image.Image:
    punched = punch_window(im)
    bbox = punched.getbbox()
    if bbox:
        punched = punched.crop(bbox)
    w, h = punched.size
    side = max(w, h, 1)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(punched, ((side - w) // 2, (side - h) // 2), punched)
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def import_frames(src: Path, out_root: Path, size: int = 1024, *, append: bool = False) -> list[Path]:
    frames_dir = out_root / "frames"
    src_copy = frames_dir / "_source"
    frames_dir.mkdir(parents=True, exist_ok=True)
    src_copy.mkdir(parents=True, exist_ok=True)

    if not append:
        for old in frames_dir.glob("frame-*.png"):
            old.unlink()

    written: list[Path] = []
    existing = sorted(frames_dir.glob("frame-*.png"))
    idx = 1
    if append and existing:
        try:
            idx = max(int(p.stem.split("-")[1]) for p in existing) + 1
        except Exception:
            idx = len(existing) + 1
    files = sorted(
        [p for p in src.iterdir() if p.suffix.lower() in {".png", ".webp", ".jpg", ".jpeg"} and p.is_file()],
        key=lambda p: p.name.lower(),
    )
    for src_path in files:
        dest = src_copy / src_path.name
        if not dest.exists() or dest.stat().st_size != src_path.stat().st_size:
            shutil.copy2(src_path, dest)
        try:
            raw = Image.open(src_path)
            raw.load()
        except Exception as e:
            print(f"skip {src_path.name}: {e}")
            continue
        parts = split_cards(raw)
        print(f"{src_path.name}: {len(parts)} card(s)")
        if (
            len(parts) == 1
            and max(raw.size) >= 1600
            and _cell_looks_like_card(np.array(raw.convert("RGBA"))) < 0.32
        ):
            print("  skip unsplit spritesheet")
            continue
        for part in parts:
            frame = normalize_frame(part, size=size)
            arr = np.array(frame)
            hole_frac = float((arr[:, :, 3] < 40).mean())
            if hole_frac < 0.08 or hole_frac > 0.82:
                print(f"  skip bad-hole {hole_frac:.1%}")
                continue
            # Reject leftover spritesheets (many separate chrome islands).
            # Allow a few decorative cutouts on legit single frames.
            solid = arr[:, :, 3] >= 40
            small_s = np.array(
                Image.fromarray((solid.astype(np.uint8) * 255), mode="L").resize(
                    (96, 96), Image.Resampling.NEAREST
                )
            ) > 127
            n_chrome = len(_components(small_s, min_area=120))
            if n_chrome >= 6:
                print(f"  skip multi-card leftover chrome_blobs={n_chrome}")
                continue
            out = frames_dir / f"frame-{idx:03d}.png"
            frame.save(out, optimize=True)
            written.append(out)
            print(f"  wrote {out.name} hole={hole_frac:.1%}")
            idx += 1
    return written


def seed_center_dirs(out_root: Path) -> None:
    centers = out_root / "centers"
    for t in range(1, 11):
        d = centers / f"t{t}"
        d.mkdir(parents=True, exist_ok=True)
        readme = d / "README.txt"
        if not readme.exists():
            readme.write_text(
                f"Drop NSFW center art for loot tier {t} here (.png/.jpg/.webp).\n"
                "One random file is composited under a random transparent frame on each roll.\n",
                encoding="utf-8",
            )
        images = [
            p
            for p in d.iterdir()
            if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ]
        if images:
            continue
        legacy = out_root / f"tier-{t}.png"
        if legacy.is_file() and legacy.stat().st_size > 0:
            shutil.copy2(legacy, d / f"_seed-from-tier-{t}.png")
            print(f"seeded centers/t{t}/ from tier-{t}.png")
    any_dir = centers / "_any"
    any_dir.mkdir(parents=True, exist_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--append", action="store_true", help="Add frames without deleting existing frame-*.png")
    args = ap.parse_args()
    if not args.src.is_dir():
        raise SystemExit(f"source not found: {args.src}")
    written = import_frames(args.src, args.out, size=args.size, append=args.append)
    seed_center_dirs(args.out)
    print(f"done: {len(written)} frames -> {args.out / 'frames'}")


if __name__ == "__main__":
    main()
