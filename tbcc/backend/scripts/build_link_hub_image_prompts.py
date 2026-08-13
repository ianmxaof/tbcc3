#!/usr/bin/env python3
"""Export link hub image prompts + button tree JSON from live affiliate DB.

  python scripts/build_link_hub_image_prompts.py
  python scripts/build_link_hub_image_prompts.py --write-md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.database.session import SessionLocal
from app.services.link_hub_image_prompt_builder import export_all_prompts
from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

TBCC_ROOT = BACKEND.parent
OUT_JSON = TBCC_ROOT / "docs" / "samples" / "link_hub_menus" / "button_tree_and_prompts.json"
OUT_MD = TBCC_ROOT / "docs" / "samples" / "link_hub_menus" / "IMAGE_PROMPTS.md"


def _write_md(data: dict) -> None:
    from app.services.aof_links_hub_menu_variants import MENU_IMAGE_FILES

    lines = [
        "# AOF LINK HUB — menu image prompts (auto-generated)",
        "",
        "Regenerate: `python backend/scripts/build_link_hub_image_prompts.py --write-md`",
        "",
        "Prompts list affiliates in **exact inline-keyboard order** (top→bottom, left→right).",
        "",
    ]
    for key, prompt in sorted(data.get("prompts", {}).items()):
        kind, variant = key.split("_", 1)
        png = MENU_IMAGE_FILES.get((kind, variant))  # type: ignore[arg-type]
        if not png:
            png = f"{key}.png"
        lines.append(f"## {png}")
        lines.append("")
        lines.append(prompt)
        lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--columns", type=int, default=2)
    p.add_argument("--write-md", action="store_true", help="Rewrite IMAGE_PROMPTS.md")
    args = p.parse_args()

    db = SessionLocal()
    try:
        data = export_all_prompts(db, columns=args.columns)
    finally:
        db.close()

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT_JSON}")

    if args.write_md:
        _write_md(data)
        print(f"Wrote {OUT_MD}")

    ai = data.get("button_tree", {}).get("ai", [])
    print(f"AI partners: {len(ai)}")
    for row in ai[:3]:
        print(f"  {row['num']} {row['label']} · {row['blurb']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
