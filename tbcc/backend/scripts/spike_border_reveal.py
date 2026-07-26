"""
Local spike: single border clip → MP4 over a tier center still.

  cd tbcc/backend
  py -3 scripts/spike_border_reveal.py --tier 5 --out reveal-border.mp4
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tier", type=int, default=5)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=Path, default=Path("reveal-border.mp4"))
    args = p.parse_args()

    from app.services.loot_border_reveal import (
        compose_border_reveal_mp4,
        list_border_clips,
        pick_border_clip,
    )
    from app.services.loot_tier_card_assets import compose_reveal_border_layers

    clips = list_border_clips()
    print(f"clips={len(clips)}")
    if not clips:
        print("Run: py -3 scripts/import_loot_border_animations.py")
        return 1

    rng = random.Random(args.seed)
    clip = pick_border_clip(rng)
    if not clip:
        print("no border clip")
        return 1
    print(f"clip={clip.name}")
    layers = compose_reveal_border_layers(args.tier, rng=rng, border_clip=clip)
    if not layers:
        print("compose_reveal_border_layers failed (need frames + centers)")
        return 1
    center_jpeg, stamp_png = layers
    mp4, note = compose_border_reveal_mp4(center_jpeg, stamp_png, rng=rng, border_clip=clip)
    if not mp4:
        print("encode failed:", note)
        return 1
    args.out.write_bytes(mp4)
    print(f"OK {args.out} ({len(mp4)//1024} KB) {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
