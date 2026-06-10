"""
Interactive Telethon login for TBCC: admin session + poster/import session copies.

- Writes/updates the admin session (dashboard thumbnails, light Telegram reads).
- Copies that SQLite session to poster + import session files so Celery/API imports
  do not share one locked DB with dashboard previews.

Prereqs: tbcc/.env with API_ID and API_HASH (from https://my.telegram.org).

Usage (must be an interactive terminal — Telegram will ask for phone / code):

  cd tbcc/backend
  python scripts/login_telethon_sessions.py

Options:
  --copy-only     Skip login; copy existing admin.session -> poster/import sessions only.
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

from app.utils.telethon_session import admin_session_stem, import_session_stem, poster_session_stem


def _copy_session_db(admin_stem: str, target_stem: str, label: str) -> None:
    admin_path = f"{admin_stem}.session"
    target_path = f"{target_stem}.session"
    if not os.path.isfile(admin_path):
        raise SystemExit(f"Admin session not found: {admin_path}")
    if os.path.normcase(os.path.normpath(admin_stem)) == os.path.normcase(
        os.path.normpath(target_stem)
    ):
        print(f"Skip {label}: admin and target session paths are the same.")
        return
    src = sqlite3.connect(admin_path)
    dst = sqlite3.connect(target_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    print(f"Copied {admin_path} -> {target_path} ({label})")


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
    parser = argparse.ArgumentParser(description="Telethon login for TBCC admin + derived sessions")
    parser.add_argument(
        "--copy-only",
        action="store_true",
        help="Only copy admin session to poster/import (no interactive login)",
    )
    args = parser.parse_args()

    admin_stem = admin_session_stem()
    poster_stem = poster_session_stem()
    import_stem = import_session_stem()

    if args.copy_only:
        _copy_session_db(admin_stem, poster_stem, "poster")
        _copy_session_db(admin_stem, import_stem, "import")
        print("Done (--copy-only). Restart Celery and the API if they are running.")
        return

    asyncio.run(_login_admin())
    print(f"Poster session file: {poster_stem}.session")
    print(f"Import session file: {import_stem}.session")
    _copy_session_db(admin_stem, poster_stem, "poster")
    _copy_session_db(admin_stem, import_stem, "import")
    print("Done. Restart Celery and the API so workers pick up the new session files.")


if __name__ == "__main__":
    main()
