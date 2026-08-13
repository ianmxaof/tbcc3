"""Pin Storage Hub lane operator manual in every forum subtopic."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()


async def main() -> int:
    import os

    from telegram import Bot

    from app.services.storage_hub_lane_manual import ensure_all_lane_manuals_pinned

    parser = argparse.ArgumentParser(description="Pin Storage Hub lane manual in every subtopic")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete stale manual messages and post fresh copies",
    )
    parser.add_argument(
        "--pause-s",
        type=float,
        default=float(os.getenv("TBCC_STORAGE_HUB_PANEL_BOOTSTRAP_PAUSE_S") or "2.5"),
        help="Pause between topics (flood control)",
    )
    args = parser.parse_args()

    token = (os.getenv("TBCC_ALBUM_COMPOSER_BOT_TOKEN") or "").strip()
    if not token:
        print(json.dumps({"ok": False, "error": "TBCC_ALBUM_COMPOSER_BOT_TOKEN missing"}))
        return 1

    bot = Bot(token)
    report = await ensure_all_lane_manuals_pinned(
        bot,
        force_new=bool(args.force),
        pause_s=max(1.0, float(args.pause_s)),
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
