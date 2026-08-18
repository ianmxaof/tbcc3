#!/usr/bin/env python3
"""Week 1 Track I: canSendStory dry-run or one flood-safe user story.

  py -3.13 scripts/telegram_story_oneshot.py --dry-run
  py -3.13 scripts/telegram_story_oneshot.py --execute --file path.jpg

Island admin.session only. Default is dry-run. Execute is operator-gated.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()


async def _run(args: argparse.Namespace) -> int:
    from app.services.telegram_story_oneshot import (
        account_lock_is_shared,
        can_send_story_dry,
        identity_cadence_note,
        send_user_story_oneshot,
        story_link_area,
    )
    from app.services.telethon_session_lock import admin_session_redis_lock
    from app.utils.telethon_session import admin_session_stem

    print("story_link:", story_link_area())
    print("account_lock_shared:", account_lock_is_shared())
    print("cadence:", identity_cadence_note(lock_contended=account_lock_is_shared()))
    if args.identity_check:
        print("identity: copied admin_poster/import/album share one auth key until a second phone is proven")
        return 0
    if not args.execute:
        print("dry-run: not opening Telethon (pass --execute on island to probe canSendStory)")
        return 0

    stem = admin_session_stem()
    from telethon import TelegramClient
    import os

    api_id = int(os.environ.get("TELEGRAM_API_ID") or "0")
    api_hash = (os.environ.get("TELEGRAM_API_HASH") or "").strip()
    if not api_id or not api_hash:
        print("missing TELEGRAM_API_ID / TELEGRAM_API_HASH")
        return 2

    with admin_session_redis_lock():
        client = TelegramClient(stem, api_id, api_hash)
        await client.connect()
        try:
            probe = await can_send_story_dry(client)
            print("canSendStory:", probe)
            if probe.get("stop"):
                return 3
            if args.file:
                out = await send_user_story_oneshot(
                    client,
                    file_path=args.file,
                    caption="Open the crate",
                )
                print("send:", out)
                return 0 if out.get("ok") else 4
        finally:
            await client.disconnect()
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--file", default="")
    p.add_argument("--identity-check", action="store_true")
    args = p.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
