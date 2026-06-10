#!/usr/bin/env python3
"""
Warm admin_poster.session entity cache for all dashboard channels.

Resolves each Channel row (numeric id + invite_link) so pool auto-post and scheduled
sends stop failing with "Cannot find any entity corresponding to -100…".

Usage (from tbcc/backend, with .env loaded):
  python scripts/warm_poster_peers.py
  python scripts/warm_poster_peers.py --update-invite 1 "https://t.me/+hMQzGsBFjF02MDkx"
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT.parent / ".env", override=True)

from app.database.session import SessionLocal
from app.models.channel import Channel
from app.utils.telegram_peer import resolve_poster_peer


async def _warm(client, ch: Channel) -> tuple[str, str]:
    title = getattr(
        await resolve_poster_peer(
            client, ch.identifier, invite_fallback=getattr(ch, "invite_link", None)
        ),
        "title",
        "?",
    )
    return ch.name or str(ch.id), title


async def main() -> int:
    parser = argparse.ArgumentParser(description="Warm poster Telethon peers for all channels")
    parser.add_argument(
        "--update-invite",
        nargs=2,
        metavar=("CHANNEL_ID", "INVITE_URL"),
        help="Set channels.invite_link then warm (e.g. 1 https://t.me/+hash)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.update_invite:
            cid, url = args.update_invite
            ch = db.query(Channel).filter(Channel.id == int(cid)).first()
            if not ch:
                print(f"Channel id={cid} not found", file=sys.stderr)
                return 1
            ch.invite_link = url.strip()
            db.commit()
            print(f"Updated invite_link for {ch.name!r} (id={ch.id})")

        rows = db.query(Channel).order_by(Channel.id).all()
    finally:
        db.close()

    if not rows:
        print("No channels in database.")
        return 0

    from app.workers.poster_worker import _get_poster_client

    client = await _get_poster_client()
    ok = 0
    fail = 0
    try:
        for ch in rows:
            try:
                name, title = await _warm(client, ch)
                print(f"OK  {ch.id} {name!r} -> {title!r} ({ch.identifier})")
                ok += 1
            except Exception as e:
                print(f"FAIL {ch.id} {ch.name!r} ({ch.identifier}): {e}", file=sys.stderr)
                fail += 1
    finally:
        await client.disconnect()

    print(f"Done: {ok} ok, {fail} failed")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
