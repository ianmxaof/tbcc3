"""
Interactive Telethon login for TBCC: admin session + poster session copy.

- Writes/updates the admin session (imports, Saved Messages, channel access).
- Copies that SQLite session to the poster session file (scheduled posts, pool posts)
  so Celery does not share one locked DB with the API process.

Prereqs: tbcc/.env with API_ID and API_HASH (from https://my.telegram.org).

Usage (must be an interactive terminal — Telegram will ask for phone / code):

  cd tbcc/backend
  python scripts/login_telethon_sessions.py

Options:
  --copy-only     Skip login; copy existing admin.session -> poster session only.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from dotenv import load_dotenv

load_dotenv(_root.parent / ".env", override=True)

from telethon import TelegramClient

from app.utils.telethon_session import admin_session_stem, poster_session_stem


def _copy_session_db(admin_stem: str, poster_stem: str) -> None:
    admin_path = f"{admin_stem}.session"
    poster_path = f"{poster_stem}.session"
    if not os.path.isfile(admin_path):
        raise SystemExit(f"Admin session not found: {admin_path}")
    if os.path.normcase(os.path.normpath(admin_stem)) == os.path.normcase(
        os.path.normpath(poster_stem)
    ):
        raise SystemExit("Admin and poster session paths are the same; nothing to copy.")
    src = sqlite3.connect(admin_path)
    dst = sqlite3.connect(poster_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    print(f"Copied {admin_path} -> {poster_path}")


async def _login_admin() -> None:
    api_id = os.environ.get("API_ID")
    api_hash = os.environ.get("API_HASH")
    if not api_id or not api_hash:
        raise SystemExit("Set API_ID and API_HASH in tbcc/.env")

    admin_stem = admin_session_stem()
    print(f"Admin session file: {admin_stem}.session")
    client = TelegramClient(admin_stem, int(api_id), api_hash)
    try:
        await client.start()
        me = await client.get_me()
        print(f"Logged in as: {me.id} @{getattr(me, 'username', None) or '(no username)'}")
    finally:
        await client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="Telethon login for TBCC admin + poster sessions")
    parser.add_argument(
        "--copy-only",
        action="store_true",
        help="Only copy admin session to poster (no interactive login)",
    )
    args = parser.parse_args()

    admin_stem = admin_session_stem()
    poster_stem = poster_session_stem()

    if args.copy_only:
        _copy_session_db(admin_stem, poster_stem)
        print("Done (--copy-only). Restart Celery and the API if they are running.")
        return

    asyncio.run(_login_admin())
    print(f"Poster session file: {poster_stem}.session")
    _copy_session_db(admin_stem, poster_stem)
    print("Done. Restart Celery and the API so workers pick up the new session files.")


if __name__ == "__main__":
    main()
