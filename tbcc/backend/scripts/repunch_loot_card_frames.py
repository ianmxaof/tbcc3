"""
One-shot: re-sanitize every frames/frame-*.png in place (baked checker → real alpha).

  cd tbcc/backend
  py -3 scripts/repunch_loot_card_frames.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.loot_tier_card_assets import frames_dir, sanitize_frame_alpha
from PIL import Image


def main() -> int:
    root = frames_dir()
    files = sorted(root.glob("frame-*.png"))
    if not files:
        print(f"no frames in {root}")
        return 1
    for p in files:
        im = Image.open(p).convert("RGBA")
        out = sanitize_frame_alpha(im)
        out.save(p, format="PNG", optimize=True)
        # quick opacity tally
        a = out.getchannel("A")
        solid = sum(1 for v in a.getdata() if v > 200)
        print(f"rewrote {p.name} opaque~{solid}")
    print(f"done {len(files)} frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
