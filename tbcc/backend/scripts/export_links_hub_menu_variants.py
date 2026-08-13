#!/usr/bin/env python3
"""Export AOF LINK HUB menu variant HTML to docs/samples/link_hub_menus/."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.aof_links_hub_menu_variants import build_all_menu_variants

OUT = BACKEND.parent / "docs" / "samples" / "link_hub_menus"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        for menu in build_all_menu_variants(db):
            name = f"{menu.kind}_{menu.variant}_{menu.title.lower().replace(' ', '_')}.html"
            path = OUT / name
            path.write_text(menu.html, encoding="utf-8")
            print(f"wrote {path}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
