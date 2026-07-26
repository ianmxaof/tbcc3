"""
Audit loot card frames for *structural* cleanliness and build frames/clean/.

Structural cleanliness (what we can measure without a text OCR pass):
  - real interior window hole   (center region alpha ~0)
  - low baked-checker residue   (opaque grey Photoshop checker cells < ~1.5%)
  - transparent-or-chrome edges (exterior is alpha hole OR solid chrome, not checker)

NOTE: "clean" here means STRUCTURAL only. Baked tier/world *text* on the frame
art is a separate problem (Phase 3 frame-selection / Phase 2 stamp-wins-visually).
We RECORD baked-text prevalence per frame (top-right opaque fraction) but do not
reject on it here — see docs/handoffs report.

Usage:
  cd tbcc/backend
  py -3 scripts/audit_loot_card_frames.py            # audit + print table
  py -3 scripts/audit_loot_card_frames.py --write     # also COPY clean frames -> frames/clean/
  py -3 scripts/audit_loot_card_frames.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.loot_tier_card_assets import frames_dir  # noqa: E402
from scripts.import_loot_card_frames import _is_checkerish  # noqa: E402

# Structural pass/fail thresholds.
MIN_WINDOW_HOLE = 0.55  # central window must be mostly a real alpha hole
MAX_CHECKER_FRAC = 0.015  # opaque baked-checker residue anywhere < 1.5%
MAX_EXTERIOR_CHECKER = 0.02  # edge ring must not be baked checker


def declutter_exterior(im: Image.Image) -> Image.Image:
    """
    No-API exterior de-checker: flood the baked grey checkerboard inward from the
    four edges, punching it to real alpha=0, stopping at the dark/neon border.

    Rescues frames that have a clean center hole but a baked *opaque* checkerboard
    margin (the import punch misses it because large checker cells only show the
    brightness step at cell boundaries). The predicate excludes dark pixels
    (mean<70) and saturated neon (chroma>26), so dark/neon borders are safe by
    construction; light/silver metal borders contiguous with the checker CAN be
    walked into, so every rescued frame must be eyeballed before promotion.
    """
    im = im.convert("RGBA")
    arr = np.array(im).astype(np.int16)
    r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    mean = (r + g + b) // 3
    ext = (a < 40) | (((mx - mn) <= 26) & (mean >= 70) & (mean <= 236))
    h, w = ext.shape
    vis = np.zeros_like(ext, dtype=bool)
    q: deque[tuple[int, int]] = deque()
    for x in range(w):
        for y in (0, h - 1):
            if ext[y, x] and not vis[y, x]:
                vis[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if ext[y, x] and not vis[y, x]:
                vis[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not vis[ny, nx] and ext[ny, nx]:
                vis[ny, nx] = True
                q.append((ny, nx))
    out = np.array(im)
    out[vis, 3] = 0
    return Image.fromarray(out, "RGBA")


def _regions(alpha: np.ndarray) -> dict[str, np.ndarray]:
    h, w = alpha.shape
    ys, xs = np.mgrid[0:h, 0:w]
    cx0, cx1 = int(w * 0.35), int(w * 0.65)
    cy0, cy1 = int(h * 0.35), int(h * 0.65)
    center = np.zeros_like(alpha, dtype=bool)
    center[cy0:cy1, cx0:cx1] = True
    t = max(2, int(min(h, w) * 0.06))
    edge = np.zeros_like(alpha, dtype=bool)
    edge[:t, :] = True
    edge[-t:, :] = True
    edge[:, :t] = True
    edge[:, -t:] = True
    # top-right quadrant = where Gemini bakes the "TIER N / world" plate
    tr = np.zeros_like(alpha, dtype=bool)
    tr[: int(h * 0.30), int(w * 0.55) :] = True
    return {"center": center, "edge": edge, "topright": tr}


def audit_frame(path: Path) -> dict:
    im = Image.open(path).convert("RGBA")
    arr = np.array(im)
    a = arr[:, :, 3]
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    h, w = a.shape
    reg = _regions(a)

    opaque = a >= 40
    checker = _is_checkerish(r, g, b) & opaque

    window_hole = float((a[reg["center"]] < 40).mean())
    checker_frac = float(checker.mean())
    edge_checker = float(checker[reg["edge"]].mean())
    # baked-text signal (informational only): opaque, non-checker chrome in top-right
    tr_opaque = float((opaque & ~checker)[reg["topright"]].mean())

    ok = (
        window_hole >= MIN_WINDOW_HOLE
        and checker_frac <= MAX_CHECKER_FRAC
        and edge_checker <= MAX_EXTERIOR_CHECKER
    )
    reasons = []
    if window_hole < MIN_WINDOW_HOLE:
        reasons.append(f"no-hole({window_hole:.0%})")
    if checker_frac > MAX_CHECKER_FRAC:
        reasons.append(f"checker({checker_frac:.1%})")
    if edge_checker > MAX_EXTERIOR_CHECKER:
        reasons.append(f"edge-checker({edge_checker:.1%})")

    return {
        "name": path.name,
        "size": [w, h],
        "window_hole": round(window_hole, 3),
        "checker_frac": round(checker_frac, 4),
        "edge_checker": round(edge_checker, 4),
        "topright_opaque": round(tr_opaque, 3),
        "clean": ok,
        "reasons": reasons,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="COPY clean frames into frames/clean/")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument(
        "--declutter-rescue",
        type=str,
        default=None,
        help=(
            "Comma list of frame numbers (e.g. 001,003,005) with a clean center hole "
            "but baked exterior checker: run the no-API de-checker and, if the result "
            "passes the audit, write the DECHECKERED png into frames/clean/. Curated "
            "keep-list — each frame was eyeballed; do not auto-promote by gate alone."
        ),
    )
    args = ap.parse_args()

    root = frames_dir()
    files = sorted(root.glob("frame-*.png"))
    if not files:
        print(f"no frames in {root}")
        return 1

    results = [audit_frame(p) for p in files]
    clean = [r for r in results if r["clean"]]
    dirty = [r for r in results if not r["clean"]]

    print(f"{'frame':16} {'hole':>6} {'check':>6} {'edgeck':>7} {'TRtext':>7}  verdict")
    for r in results:
        verdict = "CLEAN" if r["clean"] else "reject: " + ",".join(r["reasons"])
        print(
            f"{r['name']:16} {r['window_hole']:>6.2f} {r['checker_frac']:>6.2%} "
            f"{r['edge_checker']:>7.2%} {r['topright_opaque']:>7.2f}  {verdict}"
        )
    print(f"\ntotal={len(results)} clean={len(clean)} dirty={len(dirty)}")
    # baked-text prevalence among clean (informational, Phase 3 concern)
    if clean:
        hi_text = [r for r in clean if r["topright_opaque"] >= 0.15]
        print(
            f"clean frames with likely baked top-right text (TRtext>=0.15): "
            f"{len(hi_text)}/{len(clean)}"
        )

    if args.json:
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"wrote {args.json}")

    if args.write:
        clean_dir = root / "clean"
        clean_dir.mkdir(parents=True, exist_ok=True)
        for existing in clean_dir.glob("frame-*.png"):
            existing.unlink()
        n = 0
        for r in clean:
            shutil.copy2(root / r["name"], clean_dir / r["name"])
            n += 1
        print(f"COPIED {n} clean frames -> {clean_dir}  (top-level frames left untouched)")

        rescued = 0
        if args.declutter_rescue:
            nums = [s.strip() for s in args.declutter_rescue.split(",") if s.strip()]
            for num in nums:
                src = root / f"frame-{num}.png"
                if not src.is_file():
                    print(f"  rescue skip {num}: no such frame")
                    continue
                cleaned = declutter_exterior(Image.open(src))
                # Validate the DECHECKERED result against the same structural gate.
                tmp = clean_dir / f"frame-{num}.png"
                cleaned.save(tmp, optimize=True)
                a = audit_frame(tmp)
                if not a["clean"]:
                    tmp.unlink()
                    print(f"  rescue reject {num}: " + ",".join(a["reasons"]))
                    continue
                rescued += 1
                print(f"  RESCUED frame-{num}.png (decheckered) -> clean/")
            print(f"decheckered rescues written: {rescued}")
        print(f"clean pool total: {n + rescued}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
