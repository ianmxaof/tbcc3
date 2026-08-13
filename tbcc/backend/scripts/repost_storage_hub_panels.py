"""Repost Storage Hub panels at the bottom of each subtopic (operator / post-deploy)."""

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

    parser = argparse.ArgumentParser(description="Repost Storage Hub control panels at thread bottom")
    parser.add_argument("--qa-only", action="store_true", help="Q&A master panel only")
    parser.add_argument("--lanes-only", action="store_true", help="Lane deposit panels only")
    parser.add_argument(
        "--pause-s",
        type=float,
        default=float(os.getenv("TBCC_STORAGE_HUB_PANEL_BOOTSTRAP_PAUSE_S") or "2.5"),
        help="Pause between lane panels (flood control)",
    )
    args = parser.parse_args()

    token = (os.getenv("TBCC_ALBUM_COMPOSER_BOT_TOKEN") or "").strip()
    if not token:
        print(json.dumps({"ok": False, "error": "TBCC_ALBUM_COMPOSER_BOT_TOKEN missing"}))
        return 1

    bot = Bot(token)
    report: dict = {"ok": True, "sections": []}

    if not args.lanes_only:
        from app.services.qa_master_panel import ensure_qa_master_panel

        qa = await ensure_qa_master_panel(bot, force_new=True)
        report["sections"].append({"kind": "qa_master", **qa})

    if not args.qa_only:
        import os as _os

        _os.environ["TBCC_STORAGE_HUB_PANEL_BOOTSTRAP_PAUSE_S"] = str(max(1.0, args.pause_s))
        from app.services.storage_hub_control_panels import ensure_all_hub_control_panels

        hub = await ensure_all_hub_control_panels(bot, force_new=True)
        report["sections"].append({"kind": "all_hub", **hub})
        report["ok"] = bool(hub.get("ok"))

    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
