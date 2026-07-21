"""
Batch remove.bg background removal for loot card border sheets, then split +
normalize into frames/ and (optionally) promote structurally-clean ones.

This is the "Option A" pipeline: raw baked-checker Gemini sheets -> remove.bg
real-alpha PNGs -> split per card -> normalize 1024^2 -> audit -> frames/clean/.
The already-clean frame-094..101 batch was produced this exact way.

KEY HANDLING (never committed, never printed):
  - env REMOVEBG_API_KEY, OR
  - --keyfile PATH (default backend/.removebg.key, which is gitignored)
The key value is never echoed to stdout.

COST: remove.bg charges ~1 credit per full-res image (<=25 MP output). Each
2816x1536 sheet = 1 credit and yields several card frames after splitting, so
it is credit-efficient. Nothing is sent without --run (default = dry run).

Usage:
  cd tbcc/backend
  # 1) dry run — shows what WOULD be sent + credit estimate, spends nothing:
  py -3 scripts/removebg_import_loot_frames.py --only 35rrlv,6ol2c8
  # 2) actually call the API for a small test batch:
  py -3 scripts/removebg_import_loot_frames.py --only 35rrlv --run --split
  # 3) then audit + promote clean results:
  py -3 scripts/audit_loot_card_frames.py --write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.loot_tier_card_assets import frames_dir  # noqa: E402

DEFAULT_SRC = Path(
    r"C:\Users\ianmp\Downloads\tbcc\AOF NETWORK\AOF RESOURCES (ZIPS)"
    r"\AOF LOGOS\_transparent border_gemini"
)
DEFAULT_KEYFILE = Path(__file__).resolve().parents[1] / ".removebg.key"
REMOVEBG_URL = "https://api.remove.bg/v1.0/removebg"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def load_key(keyfile: Path) -> str | None:
    import os

    env = (os.getenv("REMOVEBG_API_KEY") or "").strip()
    if env:
        return env
    if keyfile.is_file():
        val = keyfile.read_text(encoding="utf-8").strip()
        if val:
            return val
    return None


def pick_sheets(src: Path, only: list[str] | None, limit: int | None) -> list[Path]:
    files = [
        p
        for p in sorted(src.iterdir())
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and "removebg" not in p.name.lower()
    ]
    if only:
        needles = [s.strip().lower() for s in only if s.strip()]
        files = [p for p in files if any(n in p.name.lower() for n in needles)]
    if limit:
        files = files[:limit]
    return files


def removebg_one(key: str, src_path: Path, out_path: Path, size: str) -> tuple[bool, str]:
    with src_path.open("rb") as fh:
        resp = requests.post(
            REMOVEBG_URL,
            headers={"X-Api-Key": key},
            files={"image_file": (src_path.name, fh, "application/octet-stream")},
            data={"size": size, "format": "png"},
            timeout=180,
        )
    remaining = resp.headers.get("X-Credits-Charged", "?")
    if resp.status_code == 200:
        out_path.write_bytes(resp.content)
        return True, f"ok charged={remaining} bytes={len(resp.content)}"
    # Do not leak the key; surface remove.bg's error text (never contains the key).
    detail = ""
    try:
        detail = resp.json().get("errors", [{}])[0].get("title", "")
    except Exception:
        detail = resp.text[:200]
    return False, f"HTTP {resp.status_code}: {detail}"


def split_and_normalize(clean_png: Path, out_frames: Path, size: int) -> int:
    """Feed a cleaned sheet through the existing import splitter -> frames/frame-*.png."""
    from PIL import Image

    from scripts.import_loot_card_frames import (
        _cell_looks_like_card,
        _components,
        normalize_frame,
        split_cards,
    )
    import numpy as np

    raw = Image.open(clean_png)
    raw.load()
    parts = split_cards(raw)
    existing = sorted(out_frames.glob("frame-*.png"))
    idx = (max((int(p.stem.split("-")[1]) for p in existing), default=0) + 1) if existing else 1
    written = 0
    for part in parts:
        frame = normalize_frame(part, size=size)
        arr = np.array(frame)
        hole = float((arr[:, :, 3] < 40).mean())
        if hole < 0.08 or hole > 0.82:
            continue
        solid = arr[:, :, 3] >= 40
        small = np.array(
            Image.fromarray((solid.astype(np.uint8) * 255), mode="L").resize(
                (96, 96), Image.Resampling.NEAREST
            )
        ) > 127
        if len(_components(small, min_area=120)) >= 6:
            continue
        out = out_frames / f"frame-{idx:03d}.png"
        frame.save(out, optimize=True)
        written += 1
        idx += 1
        print(f"    wrote {out.name} hole={hole:.0%}")
    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--keyfile", type=Path, default=DEFAULT_KEYFILE)
    ap.add_argument("--only", type=str, default=None, help="comma-substrings to filter sheets")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--size", type=str, default="auto", help="remove.bg size: preview|auto|full")
    ap.add_argument("--run", action="store_true", help="actually call remove.bg (spends credits)")
    ap.add_argument("--split", action="store_true", help="split cleaned sheets into frames/")
    ap.add_argument("--frame-size", type=int, default=1024)
    args = ap.parse_args()

    if not args.src.is_dir():
        print(f"src not found: {args.src}")
        return 2

    only = args.only.split(",") if args.only else None
    sheets = pick_sheets(args.src, only, args.limit)
    if not sheets:
        print("no matching sheets")
        return 1

    stage = frames_dir() / "_bgclean"
    stage.mkdir(parents=True, exist_ok=True)

    print(f"sheets matched: {len(sheets)} (est. ~{len(sheets)} credit(s) at size={args.size})")
    for p in sheets:
        print(f"  - {p.name}")
    if not args.run:
        print("\nDRY RUN — nothing sent. Re-run with --run (and --split) to process.")
        return 0

    key = load_key(args.keyfile)
    if not key:
        print(
            f"\nNO API KEY. Set env REMOVEBG_API_KEY or write it to {args.keyfile}\n"
            "(that path is gitignored). The key is never printed or committed."
        )
        return 3

    total_frames = 0
    for p in sheets:
        out_png = stage / f"{p.stem}-nobg.png"
        ok, msg = removebg_one(key, p, out_png, args.size)
        print(f"{p.name}: {msg}")
        if ok and args.split:
            n = split_and_normalize(out_png, frames_dir(), args.frame_size)
            total_frames += n
            print(f"  -> {n} frame(s)")
    if args.split:
        print(f"\ndone. new frames appended: {total_frames}")
        print("next: py -3 scripts/audit_loot_card_frames.py --write  # promote clean ones")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
