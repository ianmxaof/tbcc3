"""
Export a SMALL CLIP catalog scoped to the 11 AOF split lanes.

The default `tbcc/data/clip-categories.json` has ~1260 generic slugs that
don't map onto AOF network_key lanes (see clip_slug_lane_map.py / P5 of
docs/MEDIA_GATEKEEPER.md). This writes a much smaller catalog — a few
representative prompts per split lane, pulled from CLIP_SLUG_TO_LANE —
that an operator can optionally point TBCC_CLIP_CATEGORIES_FILE at.

Never overwrites the production catalog; refuses to write to any path named
clip-categories.json. Default remains the big catalog + mapper.

Usage (from tbcc/backend):
  py -3.13 scripts/export_aof_lane_clip_catalog.py
  py -3.13 scripts/export_aof_lane_clip_catalog.py --out ../data/clip-categories-aof-lanes.example.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.data.clip_slug_lane_map import CLIP_SLUG_TO_LANE, SPLIT_LANE_KEYS  # noqa: E402

MAX_SLUGS_PER_LANE = 3


def build_aof_lane_catalog(*, max_slugs_per_lane: int = MAX_SLUGS_PER_LANE) -> dict[str, Any]:
    """One/few representative CLIP_SLUG_TO_LANE prompts per split lane."""
    by_lane: dict[str, list[str]] = {lane: [] for lane in sorted(SPLIT_LANE_KEYS)}
    for slug, lanes in CLIP_SLUG_TO_LANE.items():
        for lane in lanes:
            bucket = by_lane.get(lane)
            if bucket is not None and len(bucket) < max_slugs_per_lane:
                bucket.append(slug)

    categories: list[dict[str, Any]] = []
    for lane in sorted(by_lane):
        for slug in by_lane[lane]:
            name = slug.replace("-", " ").title()
            categories.append({"slug": slug, "name": name, "prompts": [name], "group": lane})

    return {
        "categories": categories,
        "count": len(categories),
        "source": "export_aof_lane_clip_catalog.py (AOF split lanes only, not the full catalog)",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=None,
        help="Write to this path instead of stdout (never clip-categories.json)",
    )
    parser.add_argument(
        "--max-per-lane",
        type=int,
        default=MAX_SLUGS_PER_LANE,
        help="Max representative slugs per lane (default %(default)s)",
    )
    args = parser.parse_args(argv)

    catalog = build_aof_lane_catalog(max_slugs_per_lane=max(1, args.max_per_lane))
    text = json.dumps(catalog, indent=2, ensure_ascii=False)

    if args.out:
        out_path = Path(args.out)
        if out_path.name == "clip-categories.json":
            print("refusing to overwrite the production catalog file", file=sys.stderr)
            return 1
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {catalog['count']} categories -> {out_path}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
