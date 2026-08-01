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
  --copy-only        Skip login; copy existing admin.session -> poster/import sessions only.
  --quarantine-dead  Move dead admin/poster/import sessions aside, then log in fresh.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from dotenv import load_dotenv

load_dotenv(_root.parent / ".env", override=True)

from telethon import TelegramClient
from telethon.errors import AuthKeyDuplicatedError, AuthKeyUnregisteredError

from app.utils.telethon_session import admin_session_stem, import_session_stem, poster_session_stem

_DEAD_SESSION_ERRORS = (AuthKeyDuplicatedError, AuthKeyUnregisteredError)


def _session_sidecars(stem: str) -> list[Path]:
    base = Path(f"{stem}.session")
    paths = [base]
    for suffix in ("-wal", "-shm", "-journal"):
        paths.append(base.with_name(base.name + suffix))
    return paths


def _quarantine_dead_sessions(*stems: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = _root / ".session-quarantine" / stamp
    dest.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    for stem in stems:
        for path in _session_sidecars(stem):
            if not path.is_file():
                continue
            target = dest / path.name
            shutil.move(str(path), str(target))
            moved.append(path.name)
    if not moved:
        raise SystemExit("No session files found to quarantine.")
    print(f"Quarantined dead session files -> {dest}")
    for name in sorted(set(moved)):
        print(f"  - {name}")
    return dest


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


async def _login_admin(*, quarantine_dead: bool) -> None:
    api_id = os.environ.get("API_ID")
    api_hash = os.environ.get("API_HASH")
    if not api_id or not api_hash:
        raise SystemExit("Set API_ID and API_HASH in tbcc/.env")

    admin_stem = admin_session_stem()
    poster_stem = poster_session_stem()
    import_stem = import_session_stem()
    print(f"Admin session file: {admin_stem}.session")

    client = TelegramClient(admin_stem, int(api_id), api_hash)
    try:
        fresh_login = False
        try:
            await client.connect()
        except _DEAD_SESSION_ERRORS as exc:
            if not quarantine_dead:
                raise SystemExit(
                    f"{type(exc).__name__}: {exc}\n"
                    "Stop every host using this session (home tray + revenue island worker_post), "
                    "then re-run with --quarantine-dead to move dead .session files aside and log in fresh."
                ) from exc
            print(f"{type(exc).__name__}: session key is dead on disk.")
            try:
                await client.disconnect()
            except Exception:
                pass
            _quarantine_dead_sessions(admin_stem, poster_stem, import_stem)
            client = TelegramClient(admin_stem, int(api_id), api_hash)
            fresh_login = True

        if fresh_login:
            await client.start()
        elif not await client.is_user_authorized():
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
    parser.add_argument(
        "--quarantine-dead",
        action="store_true",
        help="On AuthKeyDuplicated/Unregistered, move admin/poster/import session files aside and log in fresh",
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

    asyncio.run(_login_admin(quarantine_dead=args.quarantine_dead))
    print(f"Poster session file: {poster_stem}.session")
    print(f"Import session file: {import_stem}.session")
    _copy_session_db(admin_stem, poster_stem, "poster")
    _copy_session_db(admin_stem, import_stem, "import")
    print("Done. Restart Celery and the API so workers pick up the new session files.")


if __name__ == "__main__":
    main()
