"""Bootstrap Storage Hub control panels (run on island api/worker container)."""

from __future__ import annotations

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

    from bots.storage_hub_handlers import bootstrap_storage_hub_panels

    token = (os.getenv("TBCC_ALBUM_COMPOSER_BOT_TOKEN") or "").strip()
    if not token:
        print(json.dumps({"ok": False, "error": "TBCC_ALBUM_COMPOSER_BOT_TOKEN missing"}))
        return 1
    bot = Bot(token)
    report = await bootstrap_storage_hub_panels(bot)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
