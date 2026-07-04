"""Re-wire an existing Erome album URL into pack pool (UTM promo, no upload). Run from tbcc/backend."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.database.session import SessionLocal
from app.services.erome_promo_wire import wire_erome_album_to_modifier


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Wire existing Erome album URL to pack pool modifier")
    p.add_argument("--album-url", required=True, help="https://www.erome.com/a/...")
    p.add_argument("--label", required=True, help="Pack display name / MEGA folder label")
    p.add_argument("--modifier-id", type=int, default=None, help="Update existing loot_modifiers row")
    p.add_argument("--mega-folder", default=None, help="Optional MEGA folder name for source_note theme")
    p.add_argument("--mega-dest-url", default=None, help="Optional MEGA unlock URL")
    p.add_argument("--no-refresh-scheduler", action="store_true")
    args = p.parse_args()

    with SessionLocal() as db:
        wired = wire_erome_album_to_modifier(
            db,
            album_url=args.album_url.strip(),
            label=args.label.strip(),
            modifier_id=args.modifier_id,
            mega_folder=args.mega_folder,
            mega_dest_url=args.mega_dest_url,
            refresh_scheduler=not args.no_refresh_scheduler,
        )
    print(json.dumps(wired.to_dict(), indent=2, ensure_ascii=False))
    if not wired.ok:
        print(f"ERROR: {wired.error}", file=sys.stderr)
        return 1
    print(f"mod #{wired.modifier_id} — promo: {wired.promo_note_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
