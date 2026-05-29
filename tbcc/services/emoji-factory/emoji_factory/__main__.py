"""CLI: python -m emoji_factory --input video.mp4 --cols 4 --rows 4 --out ./out"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from emoji_factory.pipeline import run_pipeline
from emoji_factory.spec import DEFAULT_CRF, DEFAULT_FPS, DEFAULT_LOOP_SEC, DEFAULT_MARGIN_PCT, DEFAULT_TILE_PX


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Split video into VP9 WebM emoji tiles")
    p.add_argument("--input", "-i", required=True, type=Path, help="Source MP4/WebM/GIF")
    p.add_argument("--out", "-o", required=True, type=Path, help="Output directory")
    p.add_argument("--cols", type=int, default=4)
    p.add_argument("--rows", type=int, default=4)
    p.add_argument("--tile-px", type=int, default=DEFAULT_TILE_PX)
    p.add_argument("--margin-pct", type=float, default=DEFAULT_MARGIN_PCT)
    p.add_argument("--fps", type=int, default=DEFAULT_FPS)
    p.add_argument("--loop-sec", type=float, default=DEFAULT_LOOP_SEC)
    p.add_argument("--crf", type=int, default=DEFAULT_CRF)
    p.add_argument("--static", action="store_true", help="Single frame per tile")
    p.add_argument("--no-normalize", action="store_true", help="Skip scale/crop to cols*tile_px canvas")
    args = p.parse_args(argv)

    try:
        manifest = run_pipeline(
            input_path=args.input,
            out_dir=args.out,
            cols=args.cols,
            rows=args.rows,
            tile_px=args.tile_px,
            margin_pct=args.margin_pct,
            fps=args.fps,
            loop_sec=args.loop_sec,
            crf=args.crf,
            static=args.static,
            normalize_canvas=not args.no_normalize,
        )
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"Wrote {manifest}")
    over = sum(1 for t in __import__("json").loads(manifest.read_text())["tiles"] if t.get("over_soft_limit"))
    if over:
        print(f"warning: {over} tile(s) exceed soft size limit — raise --crf or shorten --loop-sec")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
