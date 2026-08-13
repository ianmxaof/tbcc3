"""Import operator pose composites into companion_ui/poses/."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.companion_assets import POSE_DIR, import_operator_pose_tile, pose_tile_path
from app.services.companion_poses import POSE_SOURCE_FILES


def main() -> int:
    parser = argparse.ArgumentParser(description="Import AOF Spicy Bot pose hero JPEGs")
    parser.add_argument(
        "source_dir",
        type=Path,
        help="Directory with operator composite JPEGs",
    )
    args = parser.parse_args()
    src = args.source_dir.expanduser().resolve()
    if not src.is_dir():
        raise SystemExit(f"Not a directory: {src}")
    POSE_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    for pose_name in POSE_SOURCE_FILES:
        dest = import_operator_pose_tile(pose_name, src)
        if dest:
            print(f"OK  {pose_name} -> {pose_tile_path(pose_name).name}")
            ok += 1
        else:
            print(f"SKIP {pose_name}")
    print(f"Imported {ok}/{len(POSE_SOURCE_FILES)} pose tiles into {POSE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
