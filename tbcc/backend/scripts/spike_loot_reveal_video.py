"""
Island / local spike: one animated loot reveal MP4 (ffmpeg + backgrounds).

  docker exec infra-api-1 python scripts/spike_loot_reveal_video.py
  docker exec infra-api-1 python scripts/spike_loot_reveal_video.py --tier 8 --seed 99
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    p = argparse.ArgumentParser(description="Spike loot reveal MP4 encode on island")
    p.add_argument("--tier", type=int, default=5)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--out",
        type=Path,
        default=Path("app/data/loot_tier_cards/_spike_reveal.mp4"),
    )
    args = p.parse_args()

    import os

    os.environ.setdefault("TBCC_LOOT_REVEAL_VIDEO", "1")

    from app.services.loot_reveal_video import (
        ffmpeg_available,
        list_background_loops,
        loot_reveal_video_enabled,
    )
    from app.services.loot_tier_card_assets import build_reveal_card_mp4

    print("TBCC_LOOT_REVEAL_VIDEO:", loot_reveal_video_enabled())
    print("ffmpeg:", ffmpeg_available())
    loops = list_background_loops()
    print(f"background loops: {len(loops)}")
    for lp in loops[:8]:
        print(f"  - {lp.name} ({lp.stat().st_size // 1024} KB)")

    mp4, note = build_reveal_card_mp4(args.tier, preview={"seed": args.seed})
    print("note:", note)
    if not mp4:
        print("FAIL: no mp4 bytes")
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(mp4)
    print(f"OK wrote {args.out} ({len(mp4) // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
