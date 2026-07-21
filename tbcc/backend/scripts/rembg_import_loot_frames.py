"""
Background-remove loot card border sheets, then split + interior-punch + normalize
into a STAGING dir for review. Replaces the old remove.bg client.

Two backends (you picked Both):
  - local (default):  the `rembg` library, offline, free, unlimited. Needs
                      `py -3.13 -m pip install "rembg[cpu]"` (onnxruntime has no 3.14
                      wheels yet), so run this script with **py -3.13**. First run
                      downloads the u2net model (~176 MB) to ~/.u2net/.
  - replicate:        cjwbw/rembg hosted API. Needs REPLICATE_API_TOKEN (env or
                      gitignored backend/.replicate.key) and uploads each sheet.
                      Thin fallback for when you're off your machine.

Pipeline per sheet:  bg-remove (exterior) -> split_cards -> normalize_frame
(the latter runs punch_window to cut the interior window hole).

SAFETY: output goes to frames/_rembg/ (a staging dir the live selector ignores).
It is NEVER written to clean/ automatically — the structural audit is blind to
baked TIER text, so a "TIER 5 / DRIP" card would pass the gate and re-pollute the
pool with the wrong-tier bug. Eyeball staged frames, then copy keepers to clean/
by hand (blank-plate frames only) — see the handoff report.

Usage:
  cd tbcc/backend
  py -3.13 scripts/rembg_import_loot_frames.py --only yfb5x4                 # dry run
  py -3.13 scripts/rembg_import_loot_frames.py --only yfb5x4 --run --split    # local rembg
  py -3    scripts/rembg_import_loot_frames.py --only yfb5x4 --run --split --backend replicate
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.loot_tier_card_assets import frames_dir  # noqa: E402

DEFAULT_SRC = Path(
    r"C:\Users\ianmp\Downloads\tbcc\AOF NETWORK\AOF RESOURCES (ZIPS)"
    r"\AOF LOGOS\_transparent border_gemini"
)
REPLICATE_KEYFILE = Path(__file__).resolve().parents[1] / ".replicate.key"
# cjwbw/rembg pinned version on Replicate.
REPLICATE_MODEL = (
    "cjwbw/rembg:fb8af171cfa1616ddcf1242c093f9c46bcada5ad4cf6f2fbe8b81b330ec5c003"
)
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def pick_sheets(src: Path, only: list[str] | None, limit: int | None) -> list[Path]:
    files = [
        p
        for p in sorted(src.iterdir())
        if p.is_file()
        and p.suffix.lower() in IMAGE_EXTS
        and "removebg" not in p.name.lower()
        and "(1)" not in p.name  # skip Gemini duplicates
    ]
    if only:
        needles = [s.strip().lower() for s in only if s.strip()]
        files = [p for p in files if any(n in p.name.lower() for n in needles)]
    if limit:
        files = files[:limit]
    return files


def _remove_local(src_path: Path, out_path: Path, model: str) -> str:
    try:
        from rembg import new_session, remove
    except Exception as e:  # pragma: no cover - env guard
        raise SystemExit(
            f"rembg not importable ({e}). Run with py -3.13 after "
            'py -3.13 -m pip install "rembg[cpu]"'
        )
    from PIL import Image

    im = Image.open(src_path).convert("RGBA")
    out = remove(im, session=new_session(model))
    out.save(out_path)
    return f"local:{model} size={out.size}"


def _load_replicate_token() -> str | None:
    env = (os.getenv("REPLICATE_API_TOKEN") or "").strip()
    if env:
        return env
    if REPLICATE_KEYFILE.is_file():
        v = REPLICATE_KEYFILE.read_text(encoding="utf-8").strip()
        if v:
            return v
    return None


def _remove_replicate(src_path: Path, out_path: Path) -> str:
    token = _load_replicate_token()
    if not token:
        raise SystemExit(
            "No Replicate token. Set REPLICATE_API_TOKEN or write it to "
            f"{REPLICATE_KEYFILE} (gitignored). Never printed/committed."
        )
    import replicate  # requires: pip install replicate
    import requests

    client = replicate.Client(api_token=token)
    with src_path.open("rb") as fh:
        result = client.run(REPLICATE_MODEL, input={"image": fh})
    # cjwbw/rembg returns a URL (or file-like) to the cutout PNG.
    url = str(result)
    resp = requests.get(url, timeout=180)
    resp.raise_for_status()
    out_path.write_bytes(resp.content)
    return f"replicate bytes={len(resp.content)}"


def split_and_normalize(nobg_png: Path, stage_cards: Path, size: int) -> int:
    from PIL import Image
    import numpy as np

    from scripts.import_loot_card_frames import _components, normalize_frame, split_cards

    raw = Image.open(nobg_png)
    raw.load()
    parts = split_cards(raw)
    existing = sorted(stage_cards.glob("frame-*.png"))
    idx = (max((int(p.stem.split("-")[1]) for p in existing), default=0) + 1) if existing else 1
    written = 0
    for part in parts:
        frame = normalize_frame(part, size=size)  # runs punch_window internally
        arr = np.array(frame)
        hole = float((arr[:, :, 3] < 40).mean())
        if hole < 0.08 or hole > 0.85:
            continue
        solid = arr[:, :, 3] >= 40
        small = np.array(
            Image.fromarray((solid.astype(np.uint8) * 255), mode="L").resize(
                (96, 96), Image.Resampling.NEAREST
            )
        ) > 127
        if len(_components(small, min_area=120)) >= 6:
            continue
        out = stage_cards / f"frame-{idx:03d}.png"
        frame.save(out, optimize=True)
        written += 1
        idx += 1
        print(f"    staged {out.name} hole={hole:.0%}")
    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--only", type=str, default=None, help="comma substrings to filter sheets")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--backend", choices=("local", "replicate"), default="local")
    ap.add_argument("--model", default="u2net", help="local rembg model (u2net, isnet-general-use)")
    ap.add_argument("--run", action="store_true", help="actually remove backgrounds")
    ap.add_argument("--split", action="store_true", help="split + interior-punch into staged frames")
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

    stage = frames_dir() / "_rembg"
    stage_cards = stage / "cards"
    stage.mkdir(parents=True, exist_ok=True)

    print(f"backend={args.backend} sheets={len(sheets)}")
    for p in sheets:
        print(f"  - {p.name}")
    if not args.run:
        print("\nDRY RUN — nothing processed. Add --run (and --split).")
        return 0

    if args.split:
        stage_cards.mkdir(parents=True, exist_ok=True)
    total = 0
    for p in sheets:
        out_png = stage / f"{p.stem}-nobg.png"
        if args.backend == "local":
            msg = _remove_local(p, out_png, args.model)
        else:
            msg = _remove_replicate(p, out_png)
        print(f"{p.name}: {msg}")
        if args.split:
            n = split_and_normalize(out_png, stage_cards, args.frame_size)
            total += n
            print(f"  -> {n} staged frame(s)")
    if args.split:
        print(f"\nstaged {total} frame(s) in {stage_cards}")
        print(
            "NEXT: eyeball them. Copy ONLY blank-plate (badge-free) keepers into "
            "frames/clean/ by hand. Do NOT bulk-copy — tier-labeled cards would "
            "re-introduce the wrong-tier bug (audit can't see baked text)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
